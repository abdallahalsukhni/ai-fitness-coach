from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic
from supabase import create_client
from dotenv import load_dotenv
import voyageai
import os
import re

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
voyage_client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


# ─── Constants ─────────────────────────────────────────────────────────────────

# Minimum cosine similarity for a chunk to be included in retrieval context.
# Below this threshold, the match is semantically too weak to be useful.
MATCH_THRESHOLD = 0.3

# Hard cap on RLM retrieval steps — controls cost and prevents runaway loops.
# At 5 steps max, complex queries stay under ~7 total Claude calls per request.
MAX_RLM_STEPS = 5

SYSTEM_PROMPT = (
    "You are a fitness coach with access to the user's workout history.\n\n"
    "Only answer from the retrieved context provided. If the answer is not in the context, "
    "say so explicitly — do not guess or infer beyond what is provided.\n\n"
    "Be concise and conversational. Do not use bullet points for simple answers.\n\n"
    "If a retrieved entry is vague or lacks detail, acknowledge that and ask for specifics "
    "rather than interpreting loosely."
)


# ─── Models ────────────────────────────────────────────────────────────────────

class WorkoutLog(BaseModel):
    user_id: str
    text: str

class Query(BaseModel):
    user_id: str
    question: str


# ─── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, min_length: int = 40) -> list[str]:
    # Split on newlines and sentence boundaries — workout logs are naturally
    # structured by exercise, so sentence splits work well without sliding windows.
    raw_chunks = re.split(r'\n|(?<=[.!?])\s+', text.strip())
    # Filter chunks shorter than min_length: too short = semantically weak,
    # noisy vectors that hurt retrieval precision.
    chunks = [c.strip() for c in raw_chunks if len(c.strip()) >= min_length]
    return chunks if chunks else [text.strip()]


# ─── Contextual Chunking ───────────────────────────────────────────────────────

def add_chunk_context(full_text: str, chunk: str) -> str:
    """
    Prepend a Claude-generated context sentence to each chunk before embedding.

    Standard chunking loses surrounding context — a chunk reading "increased weight
    to 90kg" doesn't carry what exercise that was, or what came before it in the
    session. This function asks Claude to read the full workout log and generate
    one sentence that situates the chunk: the exercise, the session type, and
    exercise order when relevant (e.g. pre-fatigued muscles affect performance).

    The contextualized string is what gets embedded and stored — the vector now
    encodes both the raw content and its context within the session.
    """
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=80,
        system=(
            "Given a workout log and a specific excerpt from it, write one concise sentence "
            "that situates the excerpt. Include: what exercise or activity it describes, "
            "the session type, and if relevant, what preceded it in the session — "
            "exercise order matters because prior work affects performance. "
            "Output only that sentence, nothing else."
        ),
        messages=[{
            "role": "user",
            "content": f"Full workout log:\n{full_text}\n\nExcerpt:\n{chunk}",
        }],
    )
    context_sentence = response.content[0].text.strip()
    return f"{context_sentence} {chunk}"


# ─── Embedding ─────────────────────────────────────────────────────────────────

def embed_document(text: str) -> list[float]:
    # input_type="document" — optimizes the vector for storage/retrieval
    result = voyage_client.embed([text], model="voyage-3", input_type="document")
    return result.embeddings[0]


def embed_query(text: str) -> list[float]:
    # input_type="query" — optimizes the vector for asymmetric similarity search
    # Voyage AI trains document and query embeddings differently so that short
    # questions match against longer stored passages reliably.
    result = voyage_client.embed([text], model="voyage-3", input_type="query")
    return result.embeddings[0]


# ─── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve_chunks(query_embedding: list[float], user_id: str, count: int = 20) -> list[str]:
    # Default count=20 — intentionally over-retrieves for the reranker to select from.
    # The bi-encoder recall pass prioritizes not missing relevant chunks over precision.
    results = supabase.rpc(
        "match_workouts",
        {
            "query_embedding": query_embedding,
            "match_user_id": user_id,
            "match_count": count,
            "match_threshold": MATCH_THRESHOLD,
        },
    ).execute()
    return [r["chunk_text"] for r in results.data] if results.data else []


def hyde_embed(question: str) -> list[float]:
    """
    Hypothetical Document Embedding (HyDE — Gao et al., 2022).

    Query vectors and document vectors occupy different regions of embedding space.
    A question like "why is my bench weak?" produces a vector that doesn't look
    much like any stored workout entry. HyDE sidesteps this by generating a
    hypothetical workout entry that would answer the question, then embedding
    that document instead of the raw question.

    Uses input_type="document" — we're embedding a generated document, not a query.
    This is intentional: the whole point is to land in document space, not query space.
    """
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=80,
        system=(
            "Write a realistic 1-2 sentence workout log entry that would directly answer "
            "the following question. Write it as a plain first-person workout description, "
            "not as an answer to a question."
        ),
        messages=[{"role": "user", "content": question}],
    )
    hypothetical = response.content[0].text.strip()
    return embed_document(hypothetical)


def retrieve_chunks_hybrid(
    query_embedding: list[float], query_text: str, user_id: str, count: int = 20
) -> list[str]:
    """
    Hybrid retrieval: vector search (semantic) + BM25 full-text (keyword),
    merged with Reciprocal Rank Fusion.

    Pure semantic search misses exact matches — a question about "100kg" may
    not rank the entry containing "100kg" highly if the semantic signal is weak.
    BM25 catches keyword matches that semantic search misses. RRF rewards chunks
    that score well in both lists: 1/(60 + rank_vector) + 1/(60 + rank_bm25).
    The constant 60 is from the original RRF paper — it controls rank sensitivity.

    Requires the match_workouts_hybrid SQL function and GIN index in Supabase.
    """
    results = supabase.rpc(
        "match_workouts_hybrid",
        {
            "query_embedding": query_embedding,
            "query_text": query_text,
            "match_user_id": user_id,
            "match_count": count,
            "match_threshold": MATCH_THRESHOLD,
        },
    ).execute()
    return [r["chunk_text"] for r in results.data] if results.data else []


def rerank_chunks(query: str, chunks: list[str], top_k: int = 5) -> list[str]:
    """
    Cross-encoder reranking: second stage of two-stage retrieval.

    The bi-encoder (retrieve_chunks) encoded query and documents independently —
    fast, but imprecise. This function passes the raw query text and each candidate
    chunk text to Voyage AI's rerank-2 model, a cross-encoder that reads both
    together in a single forward pass. Every query token can attend to every
    document token, allowing it to catch synonyms, implicit connections, and
    context that cosine similarity misses.

    Can't be run against the full database (O(n) per query — too slow). Applied
    only to the small candidate set from stage 1, which is why two-stage exists.
    """
    if not chunks:
        return []
    actual_top_k = min(top_k, len(chunks))
    result = voyage_client.rerank(query, chunks, model="rerank-2", top_k=actual_top_k)
    return [item.document for item in result.results]


# ─── RLM Pipeline ──────────────────────────────────────────────────────────────

def classify_question(question: str) -> str:
    """Return 'SIMPLE' or 'COMPLEX'. Defaults to SIMPLE on any parse failure."""
    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=10,
            system=(
                "Classify the following fitness question as SIMPLE or COMPLEX.\n\n"
                "COMPLEX = requires connecting multiple data points over time "
                "(trends, plateaus, volume patterns, comparisons across weeks).\n"
                "SIMPLE = single factual lookup answerable from one retrieval pass.\n\n"
                "Respond with exactly one word: SIMPLE or COMPLEX."
            ),
            messages=[{"role": "user", "content": question}],
        )
        word = response.content[0].text.strip().upper()
        return "COMPLEX" if word == "COMPLEX" else "SIMPLE"
    except Exception:
        return "SIMPLE"


def ask_claude_what_to_retrieve(question: str, findings: list[dict]) -> str:
    """Decide what to search for next, or return 'DONE' if ready to answer."""
    findings_summary = (
        "\n".join(
            f"Step {i+1} — searched '{f['query']}': {f['finding']}"
            for i, f in enumerate(findings)
        )
        if findings
        else "No findings yet."
    )
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=60,
        system=(
            "You are directing a fitness data retrieval process. Given a question and "
            "findings collected so far, decide what to search for next in the workout history. "
            "Respond with a short search query (under 10 words), or respond with exactly "
            "'DONE' if you have enough information to answer the question."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"Findings so far:\n{findings_summary}\n\n"
                "What should I search for next?"
            ),
        }],
    )
    return response.content[0].text.strip()


def distill_finding(query: str, chunks: list[str]) -> str:
    """Compress raw retrieved chunks into a single focused finding."""
    if not chunks:
        return "No relevant data found for this query."
    context = "\n".join(f"- {c}" for c in chunks)
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=150,
        system=(
            "Distill the following workout data into a single concise finding "
            "(2-3 sentences max). Extract only what is directly relevant to the query."
        ),
        messages=[{
            "role": "user",
            "content": f"Query: {query}\n\nWorkout data:\n{context}",
        }],
    )
    return response.content[0].text.strip()


def synthesize(question: str, findings: list[dict]) -> str:
    """Final synthesis call — reasons over distilled findings, not raw chunks."""
    findings_text = "\n\n".join(
        f"Finding {i+1} (searched '{f['query']}'):\n{f['finding']}"
        for i, f in enumerate(findings)
    )
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                "Based on these retrieved findings from my workout history, answer my question.\n\n"
                f"Findings:\n{findings_text}\n\n"
                f"Question: {question}"
            ),
        }],
    )
    return response.content[0].text.strip()


def rlm_answer(question: str, user_id: str) -> dict:
    """
    Recursive retrieval loop. Each step the model decides what to search for
    next based on what it already found. Each sub-call receives only distilled
    findings — not raw chunks — keeping context small and focused.
    """
    findings = []

    for _ in range(MAX_RLM_STEPS):
        next_query = ask_claude_what_to_retrieve(question, findings)

        if next_query.upper() == "DONE":
            break

        q_embedding = embed_query(next_query)
        raw_chunks = retrieve_chunks_hybrid(q_embedding, next_query, user_id, count=10)
        reranked = rerank_chunks(next_query, raw_chunks, top_k=5)
        finding = distill_finding(next_query, reranked)
        findings.append({"query": next_query, "finding": finding})

    answer = synthesize(question, findings)
    return {"answer": answer, "steps": len(findings), "pipeline": "RLM"}


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def health_check():
    # Static response — no DB or API calls.
    # UptimeRobot pings this every 5 minutes to prevent Render cold starts.
    return {"status": "ok"}


@app.post("/log")
def log_workout(workout: WorkoutLog):
    if not workout.text.strip():
        raise HTTPException(status_code=400, detail="Workout text cannot be empty.")

    chunks = chunk_text(workout.text)
    rows = []

    for chunk in chunks:
        # Contextual chunking — prepend a Claude-generated context sentence before embedding.
        # This preserves exercise identity and session order, which raw chunks lose.
        try:
            contextualized = add_chunk_context(workout.text, chunk)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Context generation error (Anthropic): {e}")

        try:
            embedding = embed_document(contextualized)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Embedding error (Voyage AI): {e}")

        rows.append({
            "user_id": workout.user_id,
            "raw_text": workout.text,          # full original entry — used for feed display
            "chunk_text": contextualized,       # context-enriched chunk — what gets embedded and retrieved
            "embedding": embedding,             # 1024-dim vector from Voyage AI voyage-3
        })

    try:
        supabase.table("workouts").insert(rows).execute()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database error (Supabase): {e}")

    return {
        "message": "Workout logged!",
        "chunks_stored": len(rows),
        "preview": chunks[0][:120] if chunks else "",
    }


@app.get("/workouts")
def get_workouts(user_id: str, limit: int = 10):
    try:
        result = (
            supabase.table("workouts")
            .select("id, raw_text, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit * 3)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database error (Supabase): {e}")

    seen = set()
    unique = []
    for row in result.data:
        if row["raw_text"] not in seen:
            seen.add(row["raw_text"])
            unique.append(row)
        if len(unique) >= limit:
            break

    return {"workouts": unique}


@app.get("/stats")
def get_stats(user_id: str):
    from datetime import datetime, timedelta, timezone

    try:
        result = (
            supabase.table("workouts")
            .select("raw_text, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database error (Supabase): {e}")

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    seen = set()
    total = 0
    this_week = 0

    for row in result.data:
        if row["raw_text"] in seen:
            continue
        seen.add(row["raw_text"])
        total += 1
        created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        if created >= week_ago:
            this_week += 1

    return {"total_workouts": total, "this_week": this_week}


@app.delete("/workouts/{workout_id}")
def delete_workout(workout_id: int, user_id: str):
    try:
        result = (
            supabase.table("workouts")
            .select("raw_text")
            .eq("id", workout_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database error (Supabase): {e}")

    if not result.data:
        raise HTTPException(status_code=404, detail="Workout not found.")

    raw_text = result.data[0]["raw_text"]

    try:
        supabase.table("workouts").delete().eq("user_id", user_id).eq("raw_text", raw_text).execute()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database error (Supabase): {e}")

    return {"deleted": True}


@app.post("/ask")
def ask(query: Query):
    if not query.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # Classify — routes complex analytical questions to RLM, simple lookups to RAG.
    route = classify_question(query.question)

    if route == "COMPLEX":
        try:
            return rlm_answer(query.question, query.user_id)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"RLM pipeline error: {e}")

    # ── RAG pipeline ──────────────────────────────────────────────────────────

    try:
        q_embedding = embed_query(query.question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding error (Voyage AI): {e}")

    # Stage 1 — hybrid recall: vector search (semantic) + BM25 (keyword) merged via RRF.
    # Covers both failure modes: semantic search misses exact numbers/names,
    # keyword search misses conceptual queries. RRF rewards chunks that rank well in both.
    try:
        raw_chunks = retrieve_chunks_hybrid(q_embedding, query.question, query.user_id, count=20)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Retrieval error (Supabase): {e}")

    # Guard — no Claude call when context is empty.
    if not raw_chunks:
        return {
            "answer": "I don't have any data relevant to that question. Log some workouts first.",
            "pipeline": "RAG",
            "steps": 1,
        }

    # Stage 2 — precision reranking: cross-encoder reads query + each chunk jointly
    try:
        chunks = rerank_chunks(query.question, raw_chunks, top_k=5)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Reranking error (Voyage AI): {e}")

    context = "\n\n".join(
        f"[Workout {i+1}] {c}" for i, c in enumerate(chunks)
    )

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    f"My workout history (most relevant entries):\n\n"
                    f"{context}\n\n"
                    f"Question: {query.question}"
                ),
            }],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error (Anthropic): {e}")

    return {
        "answer": response.content[0].text,
        "pipeline": "RAG",
        "steps": 1,
    }
