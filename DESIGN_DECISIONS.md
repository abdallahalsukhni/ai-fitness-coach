# AI Fitness Coach — Design Decisions

A complete record of every technical decision in this project, with reasoning for each choice.

---

## 1. What this project is

An AI fitness coach that lets users log workouts in plain English and ask natural language questions about their history. The core technical feature is a **hybrid RAG and RLM pipeline built entirely from scratch** — no LangChain, no LlamaIndex, no abstraction frameworks. Every decision was deliberate.

---

## 2. The full pipeline

### Log path (`POST /log`)

```
User logs a workout in plain English
  → chunk_text(): split on sentence boundaries + newlines, drop < 40 chars
  → for each chunk:
      → add_chunk_context(): Claude generates one sentence situating the chunk
            (exercise identity, session type, exercise order)
      → embed_document(): Voyage AI voyage-3, input_type="document"
      → store { user_id, raw_text, chunk_text (contextualized), embedding }
```

### Ask path (`POST /ask`)

```
User asks a question
  → classify_question(): Claude → "SIMPLE" or "COMPLEX"

  [SIMPLE → RAG]
    → embed_query(): Voyage AI voyage-3, input_type="query"
    → Stage 1 — hybrid recall (retrieve_chunks_hybrid):
          vector search (cosine similarity, pgvector) +
          BM25 full-text (tsvector + ts_rank)
          merged via Reciprocal Rank Fusion → top 20 candidates
    → Stage 2 — cross-encoder reranking (rerank_chunks):
          Voyage AI rerank-2, reads query + each chunk jointly
          → top 5 by relevance score
    → inject top 5 into Claude with SYSTEM_PROMPT → answer

  [COMPLEX → RLM, up to MAX_RLM_STEPS = 5]
    → ask_claude_what_to_retrieve(): decide what to search for next, or "DONE"
    → embed_query() + hybrid retrieval + reranking
    → distill_finding(): compress chunks into a 2–3 sentence finding
    → repeat
    → synthesize(): reason over all distilled findings → answer
```

**Why this matters:** the model never hallucinates facts about the user's workouts because it only answers from retrieved real data. Every response is grounded.

---

## 3. Why no LangChain or LlamaIndex

Both frameworks abstract away the exact components this project is designed to demonstrate: chunking, contextual enrichment, asymmetric embedding, hybrid retrieval, reranking, and multi-step reasoning loops.

Using LangChain would mean calling `RAGChain.run(question)` — one line that hides all the interesting work. Building it manually means being able to describe each step, the tradeoffs of each decision, and what could go wrong at each stage.

---

## 4. Contextual chunking

**What:** before embedding each chunk, Claude generates one sentence situating the chunk within the full workout log. That sentence is prepended before embedding — the enriched string is what gets stored and retrieved.

**Why:** standard chunking loses surrounding context. A chunk reading "increased weight to 90kg, hit all reps" doesn't carry what exercise that was. Worse, exercise order matters — if tricep pushdowns came before bench press, the bench press chunk should carry that context because pre-fatigue affects performance. The context sentence captures both.

**Example output:**
> "This is from a chest session where tricep work preceded bench pressing." increased weight to 90kg, hit all reps.

**Tradeoff:** one extra Claude call per chunk at log time. Acceptable here because logging is infrequent — you pay at write time, not read time.

**Reference:** Anthropic's "Contextual Retrieval" (2024).

---

## 5. Embedding model — Voyage AI voyage-3

**What was considered:** OpenAI `text-embedding-3-small`, Cohere.

**Why Voyage AI:**
- Anthropic acquired Voyage AI specifically for their embedding quality — a natural fit for an Anthropic-stack project.
- `voyage-3` is purpose-built for retrieval tasks, optimized for semantic similarity search.
- Free tier (50M tokens/month) with no credit card required to start.

**Why not OpenAI embeddings:** introduces a second vendor for no technical benefit and breaks the coherence of the Anthropic stack.

**Dimension choice (1024):** large enough for semantic precision, small enough for fast similarity search and cheap storage.

---

## 6. Asymmetric retrieval — input_type matters

When embedding with Voyage AI, different `input_type` values are used:

- **Logging a workout:** `input_type="document"` — treats the text as a passage to be stored and retrieved
- **Asking a question:** `input_type="query"` — treats the text as a search query

This is **asymmetric retrieval**. The embedding space for queries and documents is slightly different. A question like "how is my bench press progressing?" should match against entries like "bench press 4 sets 80kg" even though the words don't overlap. Using the wrong `input_type` for queries degrades retrieval quality.

---

## 7. Hybrid search — vector + BM25 + Reciprocal Rank Fusion

**What:** the Supabase RPC `match_workouts_hybrid` runs both a pgvector cosine similarity search and a Postgres full-text search (BM25 via `tsvector`/`ts_rank`) in parallel, then merges the two ranked lists using Reciprocal Rank Fusion. RRF formula: `1/(60 + rank_vector) + 1/(60 + rank_bm25)`. The constant `k=60` is from the original RRF paper and controls rank sensitivity.

**Why:** pure semantic search misses keyword-sensitive queries. "When did I bench 100kg?" — the vector might not strongly encode the exact number "100kg." BM25 catches it by exact term match. Pure keyword search misses semantic queries. Neither alone dominates. RRF rewards chunks that rank well in both lists.

**Tradeoff:** requires a GIN full-text index on `chunk_text` in Postgres and two DB queries instead of one, merged in SQL.

**Eval finding:** hybrid scored identically to pure vector search (76.7% hit@5) on the seed dataset of ~17 entries. Likely because the corpus is small enough that vector recall is already near-ceiling — BM25 adds no signal when the bi-encoder already retrieves the relevant chunks. The architecture is correct at scale; the dataset is the limiting factor.

---

## 8. Two-stage retrieval + cross-encoder reranking

**What:** Stage 1 retrieves 20 candidates fast with pgvector (bi-encoder). Stage 2 re-scores those 20 using Voyage AI's `rerank-2` model (cross-encoder, reads query + document jointly).

**Why:** the bi-encoder encodes query and document independently — fast, but imprecise, because the two vectors never interact. The cross-encoder sees both in the same forward pass, so every query token can attend to every document token. It catches synonyms, implicit connections, and context that cosine similarity misses. But it's O(n) per query — you can't run it against the full database. Two-stage: bi-encoder for recall, cross-encoder for precision.

**Tradeoff:** one extra Voyage AI API call per query. Small latency increase, material precision improvement.

---

## 9. RLM pipeline (Recursive LLM)

**What:** a query classifier routes complex analytical questions to a recursive retrieval loop. The loop runs up to `MAX_RLM_STEPS = 5`. Each step: Claude decides what sub-query to run next → hybrid retrieval → reranking → distillation (chunks → 2–3 sentence finding). Final synthesis call reasons over all distilled findings.

**Why:** a single retrieval pass can't answer "why is my strength plateauing?" — it requires connecting bench press trends, accessory work consistency, volume patterns, and training frequency. Each finding should inform what to look for next. The loop lets the model build understanding iteratively.

**Key design decisions:**
- Each step receives only distilled findings, not raw chunks — keeps the context window small and focused.
- `MAX_RLM_STEPS = 5` is a hard cap. At 5 steps, a complex query stays under ~7 total Claude calls. Without a cap, a poorly-formed question could loop indefinitely.
- Final synthesis reasons over findings, not raw chunks. The distillation step is what makes this practical — without it, the synthesis context would grow unmanageably large.

**Tradeoff:** multiple API calls per complex query. Slower and more expensive than single-pass RAG. Routed only when the classifier determines the question genuinely requires multi-step reasoning.

---

## 10. HyDE — implemented, evaluated, not used

**What:** `hyde_embed(question)` generates a hypothetical workout entry that would answer the question, then embeds it with `input_type="document"` instead of embedding the raw question.

**Why it was tried:** query vectors and document vectors occupy different regions of embedding space. HyDE bridges this by converting the question into document register before embedding.

**Why it was rejected:** workout logs contain specific numerical data — exact weights, times, reps. HyDE's generation produces plausible but imprecise approximations ("benched around 80-85kg") rather than the specific phrasing stored ("80kg — first time over 80, big milestone"). For a domain where exact specifics matter, asymmetric embedding already handles the distribution gap adequately. HyDE adds value in open-ended domains where the hypothetical is a close approximation of real documents. Here, specificity dominates.

**The function is retained in `backend/main.py`** as documentation of the decision and for future testing on different query types.

**Reference:** Gao et al., "Precise Zero-Shot Dense Retrieval without Relevance Labels" (2022).

---

## 11. Retrieval eval framework

**What:** `backend/eval.py` — a standalone script measuring hit@5 across retrieval modes (baseline, HyDE, hybrid). 30 labeled question-keyword pairs designed around the seed data. A hit = any expected keyword appears in any of the top-5 retrieved and reranked chunks.

**Why hit@5 and not precision@5:** the goal is whether the right information is available to the LLM, not whether every retrieved chunk is relevant. One correct chunk in the top 5 is enough for a correct answer.

**Three question categories in the eval set:**
- Keyword-sensitive: specific numbers, times, weights that semantic search may miss
- Semantic: conceptual queries that keyword search can't match
- Mixed: require both

The eval drove the decision to keep asymmetric embedding over HyDE and confirmed that hybrid search has no measurable advantage at this dataset size.

---

## 12. Vector database — pgvector on Supabase

**What was considered:** Pinecone, Weaviate, Qdrant, Chroma (local).

**Why pgvector:** the project already uses Supabase (Postgres) for auth and data. Adding pgvector as an extension means one database, one connection. There is no sync problem between a separate vector store and a relational database — they are the same database.

**Tradeoff vs dedicated vector DBs:** Pinecone would give faster ANN at very large scale. For hundreds (not billions) of vectors, pgvector's performance is identical in practice. The simplicity win is real; the performance loss is theoretical.

---

## 13. Similarity search — IVFFlat index and cosine distance

```sql
create index workouts_embedding_idx
  on workouts
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);
```

**IVFFlat vs HNSW:** pgvector supports both. IVFFlat partitions vectors into lists and searches the nearest lists. HNSW builds a hierarchical graph and is generally faster and more accurate but uses significantly more memory. IVFFlat with `lists=100` is sufficient and lighter at this scale.

**Cosine similarity vs dot product vs L2:** cosine similarity measures the angle between vectors, not magnitude. This is correct for semantic similarity — a long detailed workout log and a short one about the same exercise should match regardless of text length. L2 is sensitive to magnitude. Cosine is the standard choice for text embeddings.

**`MATCH_THRESHOLD = 0.3`:** queries only return results with similarity > 0.3. This prevents Claude from receiving completely unrelated workout entries as context when the user asks about something not in their history — the response then says "I don't have data on that" rather than hallucinating from irrelevant context.

---

## 14. LLM — Claude for reasoning, not retrieval

Claude (`claude-sonnet-4-6`) handles only reasoning steps: contextual chunking at log time, question classification, RLM sub-query decisions, finding distillation, and final answer synthesis. It never touches vector search.

**Separation of concerns:**
- Voyage AI → embedding and retrieval (what to look at)
- Claude → reasoning (what to say about it)

**The system prompt** is engineered to prevent three failure modes:
1. Hallucination — answering beyond the retrieved context
2. Self-contradiction — saying "I don't have that information" then quoting it
3. Over-verbosity — bullet-pointing a simple answer

---

## 15. Backend — FastAPI

**Why FastAPI over Flask:** FastAPI generates OpenAPI docs automatically (`/docs`), has built-in request validation via Pydantic, and supports async. For a REST API that calls external services (Voyage AI, Supabase, Anthropic), async handling matters.

**Why Python over Node/Go:** the AI/ML ecosystem is Python-first. Voyage AI, Anthropic, and Supabase all have mature Python SDKs.

**Why no ORM:** the Supabase Python client provides a clean query interface. Adding SQLAlchemy on top of a client that already abstracts SQL would be redundant complexity.

---

## 16. Frontend — React (Create React App)

**Why not Next.js:** this is a client-side application with no server-side rendering requirements. No SEO needed, no static generation needed. Next.js adds build complexity for zero benefit here.

**Why native fetch over axios:** axios adds ~14kb for functionality that `fetch` provides natively in every modern browser.

---

## 17. Authentication — Supabase Google OAuth

**Why not custom auth:** building custom authentication means handling password hashing, token refresh, session invalidation, and brute-force protection. Supabase Auth with Google OAuth handles all of it in ~20 lines of frontend code.

**How user_id works:** after Google sign-in, Supabase provides a UUID (`user.id`). This UUID is passed to every backend request. All Supabase queries filter by `user_id`, so each user sees only their own data.

**Security note:** the backend trusts the client-provided `user_id` — acceptable for a portfolio project. In production, the backend would verify the Supabase JWT on each request to prevent a user from querying another's data by sending a different UUID.

---

## 18. Deployment

| Component | Platform | Why |
|---|---|---|
| Backend | Render | Simple Python deployment, free tier, auto-deploys from GitHub |
| Frontend | Vercel | Industry standard for React, CDN delivery, preview deployments |
| Database | Supabase | Managed Postgres with pgvector, free tier, built-in auth |

**The Render cold start problem:** Render's free tier spins down instances after 15 minutes of inactivity, causing ~30 second cold starts. Solution: UptimeRobot (free) pings `GET /` every 5 minutes. The health check endpoint returns a static string — no API keys, no database calls, zero cost.

---

## 19. Known limitations

1. **JWT verification on the backend:** currently the backend trusts the client-provided `user_id`. A production system would verify the Supabase JWT on every request.

2. **Chunking sophistication:** the current regex chunker is naive. A production system would use token-aware chunking (respect model context windows) and potentially sentence transformers for better boundary detection.

3. **Embedding cache:** identical text gets re-embedded. A hash-based cache would avoid redundant Voyage AI calls.

4. **Similarity threshold tuning:** `MATCH_THRESHOLD = 0.3` was chosen by inspection. A production system would tune it on a labeled evaluation set measuring precision and recall at different thresholds.

5. **Rate limiting:** the API has no per-user rate limiting. A production deployment would add limits to prevent runaway API costs.

6. **Streaming responses:** Claude supports streaming. For long responses, streaming would render the answer token-by-token — materially better UX. Not implemented because it's incompatible with the RLM path (can't stream while the loop is still running without significant UX rethinking).
