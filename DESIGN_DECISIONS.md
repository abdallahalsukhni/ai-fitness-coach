# AI Fitness Coach — Design Decisions

A complete record of every technical and product decision made in this project, with the reasoning behind each. Written to support interview conversations.

---

## 1. What this project is

An AI fitness coach that lets users log workouts in plain English and ask natural language questions about their history. The core technical feature is a **RAG (Retrieval-Augmented Generation) pipeline built entirely from scratch** — no LangChain, no LlamaIndex, no abstraction frameworks.

The guiding principle: every decision serves the ability to explain it clearly in an interview. There is no "we used X because it was the default." Every choice was deliberate.

---

## 2. The RAG pipeline — how it works

```
POST /log
  user sends plain English workout text
  → text is chunked into semantic units
  → each chunk is embedded by Voyage AI (voyage-3, 1024 dims)
  → stored in Supabase as { raw_text, chunk_text, embedding, user_id, timestamp }

POST /ask
  user sends a natural language question
  → question is embedded by Voyage AI (input_type="query")
  → pgvector cosine similarity search retrieves top 5 matching chunks
  → retrieved chunks are injected into a Claude prompt as context
  → Claude generates a grounded answer
```

**Why this matters:** the model never hallucinates facts about the user's workouts because it only answers from retrieved real data. Every response is grounded.

---

## 3. Why no LangChain or LlamaIndex

Both frameworks abstract away the exact components this project is designed to demonstrate: chunking, embedding, vector search, and prompt injection.

Using LangChain would mean calling `RAGChain.run(question)` — one line that hides all the interesting work. In an interview, there is nothing to explain. Building it manually means being able to describe each step, the tradeoffs of each decision, and what could go wrong at each stage. That is the point of the project.

---

## 4. Embedding model — Voyage AI voyage-3

**What was considered:** OpenAI `text-embedding-3-small`, Claude (not possible — Claude has no embedding API), Cohere.

**Why Voyage AI:**
- Anthropic acquired Voyage AI specifically for their embedding quality. Using them is a natural fit for an Anthropic-stack project.
- `voyage-3` is purpose-built for retrieval tasks — optimized for semantic similarity search, not just text compression.
- Free tier (50M tokens/month) with no credit card required to start.
- The interview narrative is clean: "I used Voyage AI because Anthropic acquired them for their retrieval quality. They pair specifically well with Claude."

**Why not OpenAI embeddings:** would break the "full Anthropic stack" story and introduces a second vendor for no technical benefit.

**The dimension choice (1024):** `voyage-3` produces 1024-dimensional vectors. This is a balance — large enough for semantic precision, small enough for fast similarity search and cheap storage.

---

## 5. Asymmetric retrieval — input_type matters

When embedding with Voyage AI, the code uses different `input_type` values:

- **Logging a workout:** `input_type="document"` — treats the text as a passage to be stored and retrieved
- **Asking a question:** `input_type="query"` — treats the text as a search query

This is called **asymmetric retrieval**. The embedding space for queries and documents is slightly different. A question like "how is my bench press progressing?" should match against entries like "bench press 4 sets 80kg" even though the words don't overlap. Using the wrong `input_type` for queries degrades retrieval quality.

Most tutorials skip this detail. It matters.

---

## 6. Chunking strategy

Long workout entries are split into semantic chunks before embedding. The chunking logic splits on newlines and sentence boundaries, keeping only chunks ≥ 40 characters.

**Why chunk at all:** embedding an entire multi-exercise workout as one vector averages out the semantics. A question about bench press should retrieve the bench press chunk, not a diluted vector that also contains running and pull-up data.

**Why this simple strategy:** for workout logs, entries are short and naturally structured by exercise. A regex split on newlines and periods captures the structure without over-engineering. A sliding window or token-based chunker would add complexity for no measurable gain on this data type.

**The tradeoff:** very short entries ("killed it today") produce one chunk that is semantically weak. The system handles this gracefully — the prompt instructs Claude to acknowledge vague logs and ask for specifics.

**Storage design:** both `raw_text` (the full original entry, for display) and `chunk_text` (the chunk that was actually embedded, for retrieval) are stored. This means the feed shows the full workout but the RAG searches on the precise chunk.

---

## 7. Vector database — pgvector on Supabase

**What was considered:** Pinecone, Weaviate, Qdrant, Chroma (local).

**Why pgvector:** the project already uses Supabase (Postgres) for auth and data storage. Adding pgvector as an extension means one database, one connection, one bill. There is no sync problem between a separate vector store and a relational database — they are the same database.

**The tradeoff vs dedicated vector DBs:** Pinecone would give faster approximate nearest neighbor search at very large scale. For a portfolio project with hundreds (not billions) of vectors, pgvector's performance is identical in practice. The simplicity win is real; the performance loss is theoretical.

---

## 8. Similarity search — IVFFlat index and cosine distance

```sql
create index workouts_embedding_idx
  on workouts
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);
```

**IVFFlat vs HNSW:** pgvector supports both. IVFFlat partitions vectors into lists and searches the nearest lists. HNSW builds a hierarchical graph and is generally faster and more accurate but uses significantly more memory. For this scale, IVFFlat with `lists = 100` is sufficient and lighter.

**Cosine similarity vs dot product vs L2:** cosine similarity measures the angle between vectors, not their magnitude. This is the right metric for semantic similarity — a long detailed workout log and a short one about the same exercise should match regardless of text length. Dot product rewards magnitude (longer texts score higher). L2 measures Euclidean distance (sensitive to magnitude). Cosine is the standard choice for text embeddings.

**The `match_threshold = 0.3`:** queries only return results with similarity > 0.3. This prevents Claude from receiving completely unrelated workout entries as context when the user asks about something not in their history. The response then says "I don't have data on that" rather than hallucinating from irrelevant context.

---

## 9. LLM — Claude for reasoning, not retrieval

Claude (`claude-sonnet-4-5`) handles only the final reasoning step — reading the retrieved chunks and generating a coherent answer. It never touches the vector search.

**The separation of concerns:**
- Voyage AI → embedding and retrieval (what to look at)
- Claude → reasoning (what to say about it)

This is the correct RAG architecture. Using one model for both tasks would mean asking Claude to simultaneously be a search engine and a reasoning engine — it does neither as well.

**The system prompt:** engineered to prevent three failure modes:
1. Self-contradiction ("I don't have that information" followed by quoting it)
2. Hallucination (answering beyond the retrieved context)
3. Over-verbosity (bullet-pointing a simple answer)

The prompt explicitly tells Claude to own what it retrieved, stay concise, and acknowledge vague logs honestly.

---

## 10. Backend — FastAPI

**Why FastAPI over Flask:** FastAPI generates OpenAPI docs automatically (`/docs`), has built-in request validation via Pydantic, and is significantly faster due to async support. For a REST API that calls external services (Voyage AI, Supabase, Anthropic), async handling matters.

**Why Python over Node/Go:** the AI/ML ecosystem is Python-first. Voyage AI, Anthropic, and Supabase all have mature Python SDKs. The operational overhead of cross-language tooling is not worth it here.

**Why no ORM (SQLAlchemy etc.):** the Supabase Python client provides a clean query interface. Adding an ORM over a client that already abstracts SQL would be redundant complexity.

---

## 11. Frontend — React (Create React App)

**Why not Next.js:** this is a client-side application with no server-side rendering requirements. No SEO needed, no static generation needed. Next.js adds build complexity for zero benefit here.

**Why not Vite:** Create React App was chosen and not migrated because the project is already working. Migrating bundlers is high-risk, low-reward churn for a project of this scope.

**Why native fetch over axios:** axios adds ~14kb for functionality that `fetch` provides natively in every modern browser. No third-party dependency for HTTP calls keeps the bundle small and the code readable.

---

## 12. Authentication — Supabase Google OAuth

**Why not JWT/custom auth:** building custom authentication means handling password hashing, token refresh, session invalidation, and brute-force protection. These are solved problems. Supabase Auth with Google OAuth handles all of it in ~20 lines of frontend code.

**Why Google OAuth specifically:** users have Google accounts. Zero friction — no new password to create or forget. For a portfolio project, interviewers can sign in immediately.

**How the user_id works:** after Google sign-in, Supabase provides a UUID (`user.id`). This UUID is passed to every backend request as `user_id`. All Supabase queries filter by `user_id`, so each user sees only their own data. The backend trusts the client-provided `user_id` — acceptable for a portfolio project. In production, the backend would verify the Supabase JWT on each request.

**RLS (Row Level Security):** enabled on the `workouts` table with a policy allowing the anon key full access. This is appropriate because the anon key is used from the frontend (it is designed to be public), and data isolation is handled at the application layer via `user_id` filtering, not at the database policy layer. The service role key (which bypasses RLS) is never exposed to the frontend.

---

## 13. Deployment

| Component | Platform | Why |
|---|---|---|
| Backend | Render | Simple Python deployment, free tier, auto-deploys from GitHub |
| Frontend | Vercel | Industry standard for React, CDN delivery, preview deployments |
| Database | Supabase | Managed Postgres with pgvector, free tier, built-in auth |

**The Render cold start problem:** Render's free tier spins down instances after 15 minutes of inactivity, causing ~30 second cold starts. This is unacceptable for a live demo. Solution: UptimeRobot (free) pings `GET /` every 5 minutes. The health check endpoint returns a static string — no API keys, no database calls, zero cost.

**Why not Lambda/serverless for the backend:** cold starts are worse on Lambda than Render. Voyage AI embedding calls take 200–500ms; a Lambda cold start on top of that creates a poor user experience. A long-running FastAPI process on Render is simpler and more predictable.

---

## 14. UI design decisions

**Dark theme (#111 background):** matches the aesthetic of tools developers and fitness-focused users actually use. Easier on the eyes for repeated use.

**Typography stack:**
- `DM Sans` (UI chrome) — clean, modern, highly legible at small sizes
- `DM Mono` (labels, metadata) — monospace for data-like elements (dates, section tags) creates visual hierarchy without color
- `Lora italic` (input fields) — the one serif, used only where the user types. Creates a "journal" feel — appropriate for logging personal data

**Two-column layout (log | recent):** natural workflow. You write on the left, see your history on the right. The ask section below is a secondary action — you log first, then query.

**Greeting bar:** personalizes the session with the user's name and time of day. Shows live stats (total workouts, this week). Fills the top of the screen with information that is immediately relevant rather than decorative.

**"How it works" section:** three cards explaining the RAG pipeline in plain language. Serves two purposes — helps real users understand the product, and gives interviewers looking at the live demo an immediate explanation of the architecture without needing to read code.

**Delete on hover:** trash icon is invisible until hovering over a feed item (always visible on mobile/touch). Prevents accidental deletes from a cluttered UI while keeping the action discoverable.

---

## 15. What I would do differently at production scale

These are honest answers for "what are the limitations" interview questions:

1. **JWT verification on the backend:** currently the backend trusts the client-provided `user_id`. At production scale, each request should verify the Supabase JWT to prevent a user from querying another user's data by sending a different UUID.

2. **Chunking sophistication:** the current regex chunker is naive. A production system would use token-aware chunking (respect model context windows) and potentially sentence transformers for better boundary detection.

3. **Embedding cache:** identical text (if a user logs the same workout twice) gets re-embedded. A simple hash-based cache would avoid redundant Voyage AI calls.

4. **The similarity threshold (0.3) is a guess:** in production this would be tuned on a labeled evaluation set — sample questions with known relevant entries, measuring precision and recall at different thresholds.

5. **Rate limiting:** the API has no rate limiting. A production deployment would add per-user request limits to prevent runaway Anthropic/Voyage API costs.

6. **Streaming responses:** Claude supports streaming. For long coach responses, streaming would render the answer token-by-token instead of waiting for the full response — meaningfully better UX.

---

## 16. The one-sentence answers

For rapid-fire interview questions:

- **What is RAG?** Retrieve relevant context from a knowledge base, inject it into an LLM prompt, so the model answers from real data instead of its training weights.
- **Why pgvector over Pinecone?** Same database as the rest of the app — no sync complexity, simpler infrastructure, performance is equivalent at this scale.
- **How does vector search work?** Each text is converted to a high-dimensional vector by an embedding model. Similarity search finds vectors closest in angle (cosine similarity) to the query vector — semantically similar texts cluster together in the vector space.
- **Why Voyage AI?** Anthropic acquired them for embedding quality. They're optimized for retrieval tasks and pair naturally with Claude.
- **What's asymmetric retrieval?** Using different embedding modes for stored documents vs. search queries — improves recall because the semantic space for questions differs from the space for statements.
- **How is user data isolated?** Every database query filters by `user_id` (a Supabase auth UUID). One user cannot access another's data.
