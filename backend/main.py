from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic
from supabase import create_client
from dotenv import load_dotenv
import voyageai
import os

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


# ─── Models ────────────────────────────────────────────────────────────────────

class WorkoutLog(BaseModel):
    user_id: str
    text: str

class Query(BaseModel):
    user_id: str
    question: str


# ─── Helpers ───────────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    """Generate a 1024-dim embedding using Voyage AI voyage-3."""
    result = voyage_client.embed([text], model="voyage-3", input_type="document")
    return result.embeddings[0]


def chunk_workout(text: str) -> list[str]:
    """
    Split a workout log into semantic chunks.
    Strategy: split on newlines / sentence boundaries, keep chunks ≥ 40 chars.
    For most workout logs a single chunk is fine; this handles multi-exercise entries.
    """
    import re
    # Split on newlines or periods followed by a space
    raw = re.split(r"\n+|(?<=\.)\s+", text.strip())
    chunks = [c.strip() for c in raw if len(c.strip()) >= 40]
    # If splitting produced nothing useful, treat the whole text as one chunk
    return chunks if chunks else [text.strip()]


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "AI Fitness Coach API is running"}


@app.post("/log")
def log_workout(workout: WorkoutLog):
    """
    Receive a plain-English workout, chunk it, embed each chunk with Voyage AI,
    and store everything in Supabase (pgvector).
    """
    if not workout.text.strip():
        raise HTTPException(status_code=400, detail="Workout text cannot be empty.")

    chunks = chunk_workout(workout.text)
    rows = []

    for chunk in chunks:
        embedding = embed(chunk)
        rows.append({
            "user_id": workout.user_id,
            "raw_text": workout.text,   # full original for display
            "chunk_text": chunk,         # the portion that was embedded
            "embedding": embedding,
        })

    supabase.table("workouts").insert(rows).execute()

    return {
        "message": "Workout logged!",
        "chunks_stored": len(rows),
        "preview": chunks[0][:120] if chunks else "",
    }


@app.get("/workouts")
def get_workouts(user_id: str, limit: int = 10):
    """
    Return the most recent workout entries for a user (deduplicated by raw_text).
    Used by the frontend live feed.
    """
    result = (
        supabase.table("workouts")
        .select("id, raw_text, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit * 3)   # over-fetch to dedup by raw_text
        .execute()
    )

    # Deduplicate — multiple chunks share the same raw_text
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
    """
    Return workout stats for the stats strip: total logged, workouts this week.
    Deduplicates by raw_text so chunks don't inflate the count.
    """
    from datetime import datetime, timedelta, timezone

    result = (
        supabase.table("workouts")
        .select("raw_text, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    )

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
    """
    Delete a workout by id. Looks up the raw_text for that id, then deletes
    ALL chunks that share the same raw_text (so the full workout is removed).
    """
    result = (
        supabase.table("workouts")
        .select("raw_text")
        .eq("id", workout_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Workout not found.")

    raw_text = result.data[0]["raw_text"]
    supabase.table("workouts").delete().eq("user_id", user_id).eq("raw_text", raw_text).execute()
    return {"deleted": True}


@app.post("/ask")
def ask(query: Query):
    """
    Embed the question with Voyage AI (input_type="query"), do pgvector similarity
    search in Supabase, inject top results as context into a Claude prompt.
    """
    if not query.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # 1. Embed the question (use input_type="query" for asymmetric retrieval)
    q_embedding = voyage_client.embed(
        [query.question], model="voyage-3", input_type="query"
    ).embeddings[0]

    # 2. Vector similarity search via Supabase RPC
    results = supabase.rpc(
        "match_workouts",
        {
            "query_embedding": q_embedding,
            "match_user_id": query.user_id,
            "match_count": 5,
            "match_threshold": 0.3,
        },
    ).execute()

    # 3. Build context block
    if results.data:
        context_entries = [r["chunk_text"] for r in results.data]
        context = "\n\n".join(
            f"[Workout {i+1}] {entry}" for i, entry in enumerate(context_entries)
        )
    else:
        context = "(No relevant workouts found in history.)"

    # 4. Prompt pipeline — inject retrieved context into Claude call
    system_prompt = (
        "You are a concise, encouraging fitness coach. "
        "The user's workout entries below are your ONLY source of truth — treat them as facts. "
        "Never say you lack information about something that is clearly stated in the entries. "
        "If a log entry is vague (e.g. 'killed it today'), acknowledge it positively and "
        "suggest the user log specifics next time so you can give better feedback — keep it brief. "
        "If no entries are relevant, say so in one sentence. "
        "Do not use excessive formatting or bullet points for short answers. "
        "Be direct, warm, and under 150 words unless the question genuinely requires more detail."
    )

    user_message = (
        f"My workout history (most relevant entries):\n\n"
        f"{context}\n\n"
        f"Question: {query.question}"
    )

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    return {
        "answer": response.content[0].text,
        "sources_used": len(results.data) if results.data else 0,
    }
