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
  of the top-5 retrieved+reranked chunks. Mean hit@5 across all 30
  questions gives the pipeline's overall retrieval score (0.0 – 1.0).

Why hit@k and not precision@k:
  We care whether the right information was *available* to Claude, not
  whether every retrieved chunk was relevant. One correct chunk in the
  top 5 is enough for the model to answer correctly.

Rate limiting:
  Voyage AI free tier is 3 RPM. Each question makes 2 Voyage calls
  (embed + rerank), so we enforce a 21-second gap between consecutive
  Voyage calls. Running all 3 modes over 30 questions takes ~63 minutes.
  Each call is rate-limited individually — not once per question.
"""

import sys
import os
import time
from dotenv import load_dotenv
from supabase import create_client
import voyageai
from anthropic import Anthropic

load_dotenv()

USER_ID = "6fe06b64-be37-48a9-92e5-9ed06fb2db33"

voyage_client    = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
supabase         = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MATCH_THRESHOLD    = 0.3    # must match main.py
VOYAGE_MIN_INTERVAL = 21.0  # 3 RPM → 20s between requests; +1s buffer

# ── Rate limiting ──────────────────────────────────────────────────────────────

_last_voyage_call = 0.0


def _voyage_wait():
    """Block until it's safe to make another Voyage AI call (3 RPM free tier)."""
    global _last_voyage_call
    elapsed = time.time() - _last_voyage_call
    if elapsed < VOYAGE_MIN_INTERVAL:
        time.sleep(VOYAGE_MIN_INTERVAL - elapsed)
    _last_voyage_call = time.time()


def _voyage(fn, max_retries: int = 3):
    """
    Call fn() with per-call rate limiting and exponential-backoff retry on 429.
    fn should be a zero-arg lambda wrapping the voyage_client call.
    """
    global _last_voyage_call
    for attempt in range(max_retries):
        if attempt > 0:
            extra = 60 * (2 ** (attempt - 1))  # 60s, 120s on subsequent retries
            print(f"\n  [rate limit hit — retry {attempt}/{max_retries-1}, waiting {extra}s]", flush=True)
            time.sleep(extra)
            _last_voyage_call = 0.0  # reset so _voyage_wait() doesn't compound
        _voyage_wait()
        try:
            return fn()
        except Exception as e:
            msg = str(e).lower()
            if "rate" in msg or "429" in msg or "too many" in msg:
                if attempt == max_retries - 1:
                    raise
            else:
                raise
    raise RuntimeError(f"Voyage call failed after {max_retries} retries")


# ── Eval set ───────────────────────────────────────────────────────────────────
# 30 questions across three categories. Each entry:
#   (question, keywords) — a "hit" if ANY keyword appears in ANY top-5 chunk.
#
# Designed around the seed data in seed.py (4 weeks of workouts):
#   bench 70→75→80→82.5→85kg, pull-ups 8→10 reps best set,
#   rows 60→67.5kg, squat 80→85kg, cardio 27→25 min 5km, overhead 42.5→47.5kg

EVAL_SET = [
    # ── Keyword-sensitive ──────────────────────────────────────────────────────
    # Pure semantic search may miss the specific number or phrase.
    ("When did I first bench press over 80kg?",           ["80kg", "milestone", "first time"]),
    ("What was my fastest 5km run time?",                 ["25 minutes", "new best"]),
    ("When did I struggle on squats?",                    ["struggled", "squat"]),
    ("What weight did I squat in week 3?",                ["85kg", "squat"]),
    ("When did I hit 67.5kg on barbell rows?",            ["67.5", "row"]),
    ("Did I ever do tricep dips?",                        ["dip", "tricep"]),
    ("What overhead press weights have I used?",          ["42.5", "45", "47.5", "overhead"]),
    ("When did I first bench 85kg?",                      ["85kg", "bench", "clean"]),
    ("How many reps in my best pull-up set?",             ["10", "pull-up"]),
    ("What Romanian deadlift weights have I used?",       ["romanian", "60kg", "62.5kg", "65kg"]),

    # ── Semantic ───────────────────────────────────────────────────────────────
    # Conceptual queries that keyword search won't find by exact string match.
    ("What does my upper body pulling look like?",        ["pull-up", "row", "back"]),
    ("Have I had any sessions where I pre-fatigued?",     ["pre-fatigued", "pushdown", "weak"]),
    ("How is my leg training frequency?",                 ["squat", "leg", "friday"]),
    ("Which muscle groups do I train most often?",        ["chest", "back", "upper"]),
    ("Do I train push and pull equally?",                 ["bench", "row", "pull-up"]),
    ("What exercises have I done for my back?",           ["row", "pull-up", "back"]),
    ("Have I ever had a cardio session that felt good?",  ["felt good", "run", "cardio"]),
    ("What does my weekly training split look like?",     ["monday", "wednesday", "friday"]),
    ("Do I do any compound lower body movements?",        ["squat", "deadlift", "leg"]),
    ("Have I done any bodyweight exercises?",             ["pull-up", "dip", "bodyweight"]),

    # ── Mixed ──────────────────────────────────────────────────────────────────
    # Require both semantic understanding and specific numerical terms.
    ("Has my bench press weight been going up?",          ["70kg", "75kg", "80kg", "85kg"]),
    ("What accessory work have I done for chest?",        ["tricep", "overhead", "dip"]),
    ("How has my cardio pace changed over time?",         ["27 minutes", "26 minutes", "25 minutes"]),
    ("What's my pulling strength progression like?",      ["pull-up", "row", "sets"]),
    ("How has my squat weight changed across sessions?",  ["80kg", "82.5kg", "85kg", "squat"]),
    ("Did my rowing strength improve?",                   ["60kg", "62.5kg", "65kg", "67.5kg"]),
    ("What's my full tricep training history?",           ["tricep", "pushdown", "dip"]),
    ("Did I note any personal records or milestones?",    ["milestone", "new best", "first time"]),
    ("What was my leg training weight progression?",      ["squat", "85kg", "romanian"]),
    ("How has my upper body pushing volume changed?",     ["bench", "overhead", "chest"]),
]

assert len(EVAL_SET) == 30, f"expected 30 questions, got {len(EVAL_SET)}"


# ── Pipeline functions ─────────────────────────────────────────────────────────

def embed_query(text: str) -> list[float]:
    result = _voyage(lambda: voyage_client.embed([text], model="voyage-3", input_type="query"))
    return result.embeddings[0]


def embed_document(text: str) -> list[float]:
    result = _voyage(lambda: voyage_client.embed([text], model="voyage-3", input_type="document"))
    return result.embeddings[0]


def hyde_embed(question: str) -> list[float]:
    """Generate a hypothetical workout entry (Anthropic), embed it as a document (Voyage)."""
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
    return embed_document(hypothetical)  # document embedding, not query — see main.py hyde_embed


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
    k = min(top_k, len(chunks))
    result = _voyage(lambda: voyage_client.rerank(query, chunks, model="rerank-2", top_k=k))
    return [item.document for item in result.results]


# ── Metric ─────────────────────────────────────────────────────────────────────

def hit_at_k(chunks: list[str], keywords: list[str], k: int = 5) -> int:
    """1 if any keyword appears in any of the top-k chunks (case-insensitive)."""
    for chunk in chunks[:k]:
        if any(kw.lower() in chunk.lower() for kw in keywords):
            return 1
    return 0


# ── Eval runner ────────────────────────────────────────────────────────────────

def run_eval(user_id: str, mode: str) -> tuple[float, list[int]]:
    """Run all 30 eval questions in the given mode. Returns (mean_hit@5, per-question hits)."""
    hits = []
    n = len(EVAL_SET)
    mode_start = time.time()

    for i, (question, keywords) in enumerate(EVAL_SET):
        q_start = time.time()
        remaining_qs = n - i
        if i > 0:
            avg_s = (time.time() - mode_start) / i
            eta_min = (remaining_qs * avg_s) / 60
            eta_str = f"  ~{eta_min:.0f}min left"
        else:
            eta_str = ""

        print(f"  [{i+1:2d}/{n}] {question[:52]:<53}", end="", flush=True)

        try:
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
        except Exception as e:
            print(f"ERROR: {e}")
            hit = 0

        hits.append(hit)
        elapsed = time.time() - q_start
        running = sum(hits) / len(hits)
        print(f"{'✓' if hit else '✗'}  {elapsed:4.0f}s  running: {running:.0%}{eta_str}", flush=True)

    mean = sum(hits) / len(hits)
    return mean, hits


# ── Output ─────────────────────────────────────────────────────────────────────

def print_results(mode: str, mean: float, hits: list[int]):
    categories = ["keyword-sensitive"] * 10 + ["semantic"] * 10 + ["mixed"] * 10
    print(f"\n── {mode.upper()} ── mean hit@5: {mean:.1%}")
    print(f"{'#':<4} {'Hit':<5} {'Cat':<18} {'Question':<50} Keywords")
    print("─" * 105)
    for i, ((question, keywords), hit) in enumerate(zip(EVAL_SET, hits), 1):
        marker = "✓" if hit else "✗"
        cat = categories[i - 1]
        kw_str = ", ".join(keywords[:2])
        print(f"{i:<4} {marker:<5} {cat:<18} {question[:49]:<50} {kw_str}")

    # Per-category breakdown
    ks_hits = hits[:10]
    sem_hits = hits[10:20]
    mix_hits = hits[20:]
    print(f"\n  keyword-sensitive: {sum(ks_hits)}/10 = {sum(ks_hits)/10:.0%}")
    print(f"  semantic:          {sum(sem_hits)}/10 = {sum(sem_hits)/10:.0%}")
    print(f"  mixed:             {sum(mix_hits)}/10 = {sum(mix_hits)/10:.0%}")


def print_comparison(results: dict):
    print("\n\n── COMPARISON ──────────────────────────────────────────────────────")
    header = f"{'#':<4} {'Question':<48}"
    for m in ("baseline", "hyde", "hybrid"):
        if m in results:
            header += f"  {m[:6]:>6}"
    print(header)
    print("─" * 80)
    for i, (question, _) in enumerate(EVAL_SET, 1):
        row = f"{i:<4} {question[:47]:<48}"
        for m in ("baseline", "hyde", "hybrid"):
            if m in results:
                hit = results[m][1][i - 1]
                row += f"  {'✓' if hit else '✗':>6}"
        print(row)
    print("─" * 80)
    summary = f"  {'Mean hit@5':<46}"
    for m in ("baseline", "hyde", "hybrid"):
        if m in results:
            summary += f"  {results[m][0]:>6.1%}"
    print(summary)

    # Category breakdown per mode
    print(f"\n  {'Category':<22}", end="")
    for m in ("baseline", "hyde", "hybrid"):
        if m in results:
            print(f"  {m[:6]:>6}", end="")
    print()
    for label, sl in [("keyword-sensitive", slice(0, 10)), ("semantic", slice(10, 20)), ("mixed", slice(20, 30))]:
        print(f"  {label:<22}", end="")
        for m in ("baseline", "hyde", "hybrid"):
            if m in results:
                hits = results[m][1][sl]
                print(f"  {sum(hits)/10:>6.0%}", end="")
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

    # Upfront time estimate
    voyage_calls_per_q = 2  # embed + rerank (all modes make exactly 2 Voyage calls)
    total_voyage_calls = len(EVAL_SET) * voyage_calls_per_q * len(modes_to_run)
    est_min = (total_voyage_calls * VOYAGE_MIN_INTERVAL) / 60
    print(f"eval.py — {len(EVAL_SET)} questions × {len(modes_to_run)} mode(s) = {total_voyage_calls} Voyage calls")
    print(f"Rate limit: {VOYAGE_MIN_INTERVAL:.0f}s between each call (Voyage AI 3 RPM free tier)")
    print(f"Estimated time: ~{est_min:.0f} minutes\n")

    all_results = {}

    for m in modes_to_run:
        print(f"\n{'─'*60}")
        print(f"Mode: {m.upper()}")
        print(f"{'─'*60}")
        t0 = time.time()
        try:
            mean, hits = run_eval(USER_ID, m)
            all_results[m] = (mean, hits)
            elapsed = (time.time() - t0) / 60
            print(f"\n  ── {m} done: {mean:.1%} mean hit@5  ({elapsed:.1f} min) ──")
        except Exception as e:
            print(f"\nFATAL: {e}")

    for m, (mean, hits) in all_results.items():
        print_results(m, mean, hits)

    if len(all_results) > 1:
        print_comparison(all_results)


if __name__ == "__main__":
    main()
