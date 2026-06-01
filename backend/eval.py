"""
Retrieval eval framework — measures hit@5 across three pipeline modes.

Usage:
  python eval.py baseline   # embed_query → vector search → rerank
  python eval.py hyde       # hyde_embed  → vector search → rerank
  python eval.py hybrid     # embed_query → hybrid search → rerank
  python eval.py all        # run all three and print comparison table

Set USER_ID below to your Supabase user UUID.
Requires seed data to be loaded first (run seed.py).

Metric — hit@5:
  A question is a "hit" if at least one expected keyword appears in any
  of the top-5 retrieved+reranked chunks. Mean hit@5 across all 10
  questions gives the pipeline's overall retrieval score (0.0 – 1.0).

Why hit@k and not precision@k:
  We care whether the right information was *available* to Claude, not
  whether every retrieved chunk was relevant. One correct chunk in the
  top 5 is enough for the model to answer correctly.
"""

import sys
import os
from dotenv import load_dotenv
from supabase import create_client
import voyageai
from anthropic import Anthropic

load_dotenv()

USER_ID = "6fe06b64-be37-48a9-92e5-9ed06fb2db33"

voyage_client    = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
supabase         = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MATCH_THRESHOLD = 0.3   # must match main.py

# ── Eval set ───────────────────────────────────────────────────────────────────
# Each entry: (question, keywords — a hit if ANY keyword appears in ANY top-5 chunk)
# Split into three categories to understand where each mode wins/loses.

EVAL_SET = [
    # Keyword-sensitive: pure semantic search may miss the specific number/phrase
    ("When did I first bench press over 80kg?",        ["80kg", "milestone", "first time"]),
    ("What was my fastest 5km run time?",              ["25 minutes", "new best", "personal best"]),
    ("When did I struggle on squats?",                 ["struggled", "squat"]),

    # Semantic: keyword search won't find these by exact match
    ("What does my upper body pulling look like?",     ["pull-up", "row", "back"]),
    ("Have I had any sessions where I pre-fatigued?",  ["pre-fatigued", "pushdown", "weak"]),
    ("How is my leg training frequency?",              ["squat", "leg", "friday"]),

    # Mixed: require both semantic understanding and specific terms
    ("Has my bench press weight been going up?",       ["70kg", "75kg", "80kg", "85kg"]),
    ("What accessory work have I done for chest?",     ["tricep", "overhead", "dip"]),
    ("How has my cardio pace changed over time?",      ["27 minutes", "26 minutes", "25 minutes"]),
    ("What's my pulling strength progression like?",   ["pull-up", "row", "sets"]),
]


# ── Pipeline functions ─────────────────────────────────────────────────────────

def embed_query(text: str) -> list[float]:
    result = voyage_client.embed([text], model="voyage-3", input_type="query")
    return result.embeddings[0]


def embed_document(text: str) -> list[float]:
    result = voyage_client.embed([text], model="voyage-3", input_type="document")
    return result.embeddings[0]


def hyde_embed(question: str) -> list[float]:
    """Generate a hypothetical workout entry, embed it as a document."""
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


def retrieve_vector(query_embedding: list[float], user_id: str, count: int = 20) -> list[str]:
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


def retrieve_hybrid(query_embedding: list[float], query_text: str, user_id: str, count: int = 20) -> list[str]:
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


def rerank(query: str, chunks: list[str], top_k: int = 5) -> list[str]:
    if not chunks:
        return []
    actual_top_k = min(top_k, len(chunks))
    result = voyage_client.rerank(query, chunks, model="rerank-2", top_k=actual_top_k)
    return [item.document for item in result.results]


# ── Metric ─────────────────────────────────────────────────────────────────────

def hit_at_k(chunks: list[str], keywords: list[str], k: int = 5) -> int:
    """1 if any keyword appears in any of the top-k chunks, else 0."""
    for chunk in chunks[:k]:
        if any(kw.lower() in chunk.lower() for kw in keywords):
            return 1
    return 0


# ── Eval runner ────────────────────────────────────────────────────────────────

def run_eval(user_id: str, mode: str) -> tuple[float, list[int]]:
    """
    Run all eval questions in the given mode.
    Returns (mean_hit_at_5, per_question_hits).
    """
    hits = []

    for question, keywords in EVAL_SET:
        if mode == "hyde":
            embedding = hyde_embed(question)
            raw = retrieve_vector(embedding, user_id)
        elif mode == "hybrid":
            embedding = embed_query(question)
            raw = retrieve_hybrid(embedding, question, user_id)
        else:  # baseline
            embedding = embed_query(question)
            raw = retrieve_vector(embedding, user_id)

        reranked = rerank(question, raw, top_k=5)
        hit = hit_at_k(reranked, keywords)
        hits.append(hit)

    mean = sum(hits) / len(hits)
    return mean, hits


# ── Output ─────────────────────────────────────────────────────────────────────

def print_results(mode: str, mean: float, hits: list[int]):
    print(f"\n── {mode.upper()} ── mean hit@5: {mean:.1%}")
    print(f"{'#':<4} {'Hit':<5} {'Question':<55} Keywords")
    print("─" * 90)
    for i, ((question, keywords), hit) in enumerate(zip(EVAL_SET, hits), 1):
        marker = "✓" if hit else "✗"
        kw_str = ", ".join(keywords[:2])
        print(f"{i:<4} {marker:<5} {question[:54]:<55} {kw_str}")


def print_comparison(results: dict):
    print("\n\n── COMPARISON ──────────────────────────────────────────")
    print(f"{'#':<4} {'Question':<45} {'Base':>6} {'HyDE':>6} {'Hybrid':>7}")
    print("─" * 72)
    for i, (question, _) in enumerate(EVAL_SET, 1):
        row = f"{i:<4} {question[:44]:<45}"
        for mode in ("baseline", "hyde", "hybrid"):
            if mode in results:
                hit = results[mode][1][i - 1]
                row += f"  {'✓' if hit else '✗':>5}"
            else:
                row += f"  {'—':>5}"
        print(row)
    print("─" * 72)
    print(f"{'Mean hit@5':<49}", end="")
    for mode in ("baseline", "hyde", "hybrid"):
        if mode in results:
            print(f"  {results[mode][0]:>5.1%}", end="")
        else:
            print(f"  {'—':>5}", end="")
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if not USER_ID:
        print("ERROR: Set USER_ID at the top of eval.py before running.")
        sys.exit(1)

    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "baseline"
    valid = {"baseline", "hyde", "hybrid", "all"}

    if mode not in valid:
        print(f"Usage: python eval.py [{'|'.join(sorted(valid))}]")
        sys.exit(1)

    modes_to_run = ["baseline", "hyde", "hybrid"] if mode == "all" else [mode]
    all_results = {}

    for m in modes_to_run:
        print(f"Running {m}...", end=" ", flush=True)
        try:
            mean, hits = run_eval(USER_ID, m)
            all_results[m] = (mean, hits)
            print(f"done — {mean:.1%}")
        except Exception as e:
            print(f"ERROR: {e}")

    for m, (mean, hits) in all_results.items():
        print_results(m, mean, hits)

    if len(all_results) > 1:
        print_comparison(all_results)


if __name__ == "__main__":
    main()
