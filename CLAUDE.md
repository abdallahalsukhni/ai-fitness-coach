# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What this is

An AI fitness coach where users log workouts in plain English and ask natural language questions about their history. **This is a portfolio/interview project** — every decision serves resume bullets, not product goals. Nothing hollow: every claim must be backed by real, explainable code.

---

## Commands

**Frontend** (Create React App — `npm start`, NOT `npm run dev`):
```
cd frontend && npm start
```

**Backend**:
```
cd backend && uvicorn main:app --reload
```

**Install deps**:
```
cd backend && pip install -r requirements.txt
cd frontend && npm install
```

**Env files**: `backend/.env` needs `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`. Frontend needs `REACT_APP_SUPABASE_URL`, `REACT_APP_SUPABASE_ANON_KEY`, `REACT_APP_API_URL`.

---

## Architecture

Everything lives in two files: `backend/main.py` and `frontend/src/App.js`.

### Backend pipeline (`backend/main.py`)

**`POST /log`** — chunks text → embeds each chunk as a document → stores in Supabase.
- `chunk_text()`: splits on `\n` and sentence boundaries (`[.!?]`), drops chunks under 40 chars. The 40-char floor exists because shorter chunks produce semantically weak vectors.
- `embed_document(text)`: calls Voyage AI `voyage-3` with `input_type="document"`.
- Stores 4 fields per row: `user_id`, `raw_text` (full entry, for feed display), `chunk_text` (the embedded slice, for retrieval), `embedding` (1024-dim vector).

**`POST /ask`** — classifies question → routes to RAG or RLM → returns `{answer, pipeline, steps}`.
- `classify_question(q)`: one Claude call, returns `"SIMPLE"` or `"COMPLEX"`. COMPLEX = requires connecting data points over time (trends, plateaus). Defaults to SIMPLE on any failure.
- **RAG path** (SIMPLE): `embed_query(q)` with `input_type="query"` → Supabase RPC `match_workouts` (cosine similarity, threshold `MATCH_THRESHOLD = 0.3`) → inject top 5 chunks into Claude with `SYSTEM_PROMPT` → return answer. If no chunks pass threshold, returns without a Claude call.
- **RLM path** (COMPLEX): loop up to `MAX_RLM_STEPS = 5`. Each iteration: Claude decides what to search for next (`ask_claude_what_to_retrieve`) → `embed_query` + vector search → `distill_finding` compresses raw chunks into a 2–3 sentence finding → append to findings list. When Claude returns `DONE` or steps are exhausted, `synthesize` reasons over distilled findings (not raw chunks) and returns the answer.

The `input_type` asymmetry is intentional: Voyage AI trains document and query vectors differently so short questions match against longer stored passages reliably.

**Other endpoints**: `GET /workouts` (deduped by `raw_text`, for feed), `GET /stats` (total + this_week), `DELETE /workouts/{id}` (deletes all chunks sharing the same `raw_text`), `GET /` (health check, static — no DB calls, pinged by UptimeRobot to prevent Render cold starts).

All three external calls (Voyage AI, Supabase, Anthropic) have try/except with specific error messages. Named constants: `MATCH_THRESHOLD = 0.3`, `MAX_RLM_STEPS = 5`, `SYSTEM_PROMPT`.

### Frontend (`frontend/src/App.js`)

Single component, all state inline. Auth via Supabase Google OAuth (`supabaseClient.js`). `REACT_APP_API_URL` env var points to backend.

Every `/ask` response shows a pipeline badge: `RAG` (green) or `RLM · N retrieval steps` (blue) — makes the architecture visible in the demo without requiring explanation.

### Database (Supabase + pgvector)

One table: `workouts`. The `match_workouts` RPC is a pgvector SQL function that performs cosine similarity search — it lives in Supabase, not in Python. Index: IVFFlat with `lists=100` and `vector_cosine_ops`.

---

## Hard rules

1. No LangChain, no LlamaIndex. All RAG/RLM implemented manually.
2. Frontend is Create React App — do not migrate to Vite. Files are `.js` not `.jsx`.
3. Do not change the UI design language (colors, fonts, component style).
4. The `input_type` parameter on Voyage AI calls must stay as explicit named params — it's a resume bullet.

---

## UI design tokens

- Background: `#111` / Card surfaces: `#161616` / Accent: `#1D9E75` / Hover: `#22b585`
- Borders: `#1e1e1e` default / `#2a2a2a` focus
- Fonts: **DM Sans** (UI chrome), **DM Mono** (labels, monospace), **Lora italic** (textarea + ask input only)

---

## Resume bullets (the north star)

Every word must be backed by real working code:

- Built a hybrid RAG and RLM pipeline from scratch without abstraction frameworks, implementing chunking, embedding generation, vector similarity search, and recursive multi-step retrieval for complex analytical queries
- Integrated pgvector on Supabase as the vector store with asymmetric retrieval and cosine similarity search
- Engineered a prompt pipeline that injects retrieved context into Claude to ground responses in real user data and prevent hallucination
