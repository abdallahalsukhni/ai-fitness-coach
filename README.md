# FitCoach — AI Fitness Coach

A personal fitness coach that lets you log workouts in plain English and ask natural language questions about your history. Built on a hybrid RAG and RLM pipeline implemented from scratch — no LangChain, no LlamaIndex.

**Live demo:** [ai-fitness-coach-psi-nine.vercel.app](https://ai-fitness-coach-psi-nine.vercel.app)

---

## How it works

### Logging a workout

```
User logs a workout in plain English
  → chunk_text(): split on sentence boundaries + newlines, drop chunks < 40 chars
  → for each chunk:
      → add_chunk_context(): Claude generates one sentence situating the chunk
            (captures exercise identity, session type, and exercise order —
             pre-fatigue from earlier exercises affects performance data)
      → embed_document(): Voyage AI voyage-3, input_type="document"
      → store { user_id, raw_text, chunk_text (contextualized), embedding }
```

### Asking a question

```
User asks a question
  → classify_question(): Claude classifies as SIMPLE or COMPLEX
        COMPLEX = trends, plateaus, volume patterns over time
        SIMPLE  = single factual lookup

  [SIMPLE → RAG path]
    → embed_query(): Voyage AI voyage-3, input_type="query"
    → Stage 1 — hybrid recall:
          vector search (cosine similarity, pgvector) +
          BM25 full-text search (tsvector + ts_rank)
          merged with Reciprocal Rank Fusion → top 20 candidates
    → Stage 2 — precision reranking:
          Voyage AI rerank-2 cross-encoder reads query + each chunk jointly
          → top 5 by relevance
    → inject top 5 into Claude with grounding system prompt → answer

  [COMPLEX → RLM path, up to 5 steps]
    → ask_claude_what_to_retrieve(): Claude decides what to search for next
    → embed_query() + hybrid retrieval + reranking
    → distill_finding(): Claude compresses chunks into a 2–3 sentence finding
    → repeat until DONE or step limit reached
    → synthesize(): Claude reasons over all distilled findings → answer
```

Every response is grounded in real logged data. The model never guesses.

Every answer shows a pipeline badge — **RAG** or **RLM · N steps** — making the architecture visible in the UI without requiring explanation.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React (Create React App) |
| Backend | FastAPI (Python) |
| LLM | Claude (`claude-sonnet-4-6`) via Anthropic API |
| Embeddings | Voyage AI (`voyage-3`, 1024 dims, asymmetric retrieval) |
| Reranking | Voyage AI (`rerank-2`, cross-encoder) |
| Vector database | Supabase + pgvector |
| Full-text search | Postgres `tsvector` / `ts_rank` (BM25) |
| Auth | Supabase Auth (Google OAuth) |
| Frontend hosting | Vercel |
| Backend hosting | Render |

---

## Running locally

### Prerequisites

- Python 3.10+
- Node.js 18+
- A [Supabase](https://supabase.com) project with pgvector enabled
- API keys for [Anthropic](https://console.anthropic.com), [Voyage AI](https://dash.voyageai.com), and Supabase

### 1. Set up the database

Run `backend/supabase_setup.sql` in your Supabase SQL Editor, then `backend/supabase_rls.sql` for row-level security policies.

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

Create `backend/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

Start the server:

```bash
uvicorn main:app --reload
```

API running at `http://127.0.0.1:8000`. Docs at `http://127.0.0.1:8000/docs`.

### 3. Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```
REACT_APP_API_URL=http://127.0.0.1:8000
REACT_APP_SUPABASE_URL=https://your-project.supabase.co
REACT_APP_SUPABASE_ANON_KEY=your-anon-key
```

Start the app:

```bash
npm start
```

Frontend running at `http://localhost:3000`.

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/log` | Chunk, contextualize, embed, and store a workout |
| `GET` | `/workouts` | Fetch recent workouts for a user |
| `DELETE` | `/workouts/{id}` | Delete a workout and all its chunks |
| `GET` | `/stats` | Total workouts and this-week count |
| `POST` | `/ask` | Classify question, run RAG or RLM pipeline, return grounded answer |

---

## Project structure

```
ai-fitness-coach/
├── backend/
│   ├── main.py               # FastAPI app — all endpoints, full RAG/RLM pipeline
│   ├── eval.py               # Retrieval eval framework (hit@5 across retrieval modes)
│   ├── seed.py               # Seed data — 16 workouts across 5 weeks
│   ├── requirements.txt
│   ├── supabase_setup.sql    # Table, IVFFlat index, match_workouts + match_workouts_hybrid RPCs
│   └── supabase_rls.sql      # Row-level security policies
├── frontend/
│   └── src/
│       ├── App.js            # Full React app — single component, all state inline
│       ├── App.css
│       └── supabaseClient.js # Supabase auth client
├── render.yaml               # Render deployment config
└── DESIGN_DECISIONS.md       # Every technical decision with full reasoning
```

---

## Design decisions

See [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md) for a full writeup: why no LangChain, why Voyage AI over OpenAI embeddings, how asymmetric retrieval works, why hybrid search, how the two-stage reranking pipeline is structured, why contextual chunking, how the RLM loop is designed, and known limitations.
