# FitCoach — AI Fitness Coach

A personal fitness coach that lets you log workouts in plain English and ask natural language questions about your history. Built on a RAG pipeline implemented from scratch — no LangChain, no LlamaIndex.

**Live demo:** [ai-fitness-coach-psi-nine.vercel.app](https://ai-fitness-coach-psi-nine.vercel.app)

---

## How it works

```
Log a workout
  → text is chunked into semantic units
  → each chunk is embedded by Voyage AI (voyage-3, 1024 dims)
  → stored in Supabase with pgvector

Ask a question
  → question is embedded (asymmetric retrieval, input_type="query")
  → pgvector cosine similarity search → top 5 matching chunks
  → retrieved context injected into a Claude prompt
  → grounded answer returned
```

Every answer is based on your actual logged data. The model never guesses.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React (Create React App) |
| Backend | FastAPI (Python) |
| LLM | Claude (`claude-sonnet-4-5`) via Anthropic API |
| Embeddings | Voyage AI (`voyage-3`, 1024 dims) |
| Vector database | Supabase + pgvector |
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
| `POST` | `/log` | Embed and store a workout |
| `GET` | `/workouts` | Fetch recent workouts for a user |
| `DELETE` | `/workouts/{id}` | Delete a workout and all its chunks |
| `GET` | `/stats` | Total workouts and this-week count |
| `POST` | `/ask` | RAG query — returns a grounded coach response |

---

## Project structure

```
ai-fitness-coach/
├── backend/
│   ├── main.py               # FastAPI app — all endpoints and RAG logic
│   ├── requirements.txt
│   ├── supabase_setup.sql    # Table, index, and match_workouts RPC
│   └── supabase_rls.sql      # Row-level security policies
├── frontend/
│   └── src/
│       ├── App.js            # Full React app
│       ├── App.css
│       └── supabaseClient.js # Supabase auth client
├── render.yaml               # Render deployment config
└── DESIGN_DECISIONS.md       # Full technical design decisions document
```

---

## Design decisions

See [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md) for a full writeup covering every technical choice: why Voyage AI over OpenAI embeddings, why pgvector over Pinecone, how asymmetric retrieval works, the chunking strategy, the similarity threshold, and known limitations.
