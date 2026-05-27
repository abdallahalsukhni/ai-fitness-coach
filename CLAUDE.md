# AI Fitness Coach — Claude Code Handoff

Read this before touching anything.

---

## Project summary

An AI fitness coach where the user logs workouts in plain English. The backend parses, embeds, and stores them. When the user asks a question, the backend does vector similarity search and injects retrieved entries into a Claude prompt (RAG). Built manually — no LangChain, no LlamaIndex.

This is a portfolio/interview project. Every decision serves 4 resume bullets, not product goals.

---

## Resume bullets (the north star)

**AI Fitness Coach** | React, FastAPI, Python, Supabase, pgvector

- Built a RAG pipeline from scratch without abstraction frameworks, implementing chunking, embedding generation, vector similarity search, and context retrieval manually
- Designed and deployed a REST API backend using FastAPI, hosted on Render with a React frontend deployed on Vercel
- Integrated vector storage using pgvector on Supabase, optimizing retrieval relevance through embedding similarity thresholds
- Engineered a prompt pipeline that injects retrieved context into LLM calls to ground responses in real data and reduce hallucination

---

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React (Create React App) | Run with `npm start`, NOT `npm run dev`. Files are `.js` not `.jsx`. Plain `App.css`, not CSS Modules. |
| Backend | FastAPI (Python) | |
| Database | Supabase + pgvector | Postgres + vector search |
| LLM | Claude API | claude-sonnet-4-20250514 |
| Embeddings | Voyage AI or Claude | TBD — to be decided this session |
| Frontend hosting | Vercel | |
| Backend hosting | Render | |

---

## Architecture

```
POST /log
  → receive plain English workout text
  → chunk text
  → generate embedding (Voyage or Claude)
  → store { text, embedding, timestamp } in Supabase (pgvector)

POST /ask
  → receive question
  → generate embedding of question
  → pgvector similarity search → top N workout entries
  → inject retrieved entries into Claude prompt
  → return grounded answer
```

---

## Current status

### Done
- [x] React frontend skeleton (dark theme, running locally via `npm start`)
- [x] FastAPI backend skeleton (`/log` and `/ask` endpoints exist but not wired to real pipeline)
- [x] Supabase project created (needs verification)
- [x] UI design language finalized (see below — do not change)

### TODO — in priority order
1. **Fix the layout** — two-column layout is broken. Right column (ask card) has a giant empty void. Recommended fix: make the right column a "Recent workouts" live feed pulled from the backend. Fallback: single column, max-width ~700px.
2. **Real embedding pipeline** — chunking + embedding API call + storing vectors in Supabase
3. **Real retrieval** — pgvector similarity search on `/ask`
4. **Prompt pipeline** — inject retrieved chunks into Claude call
5. **Wire frontend to real backend responses**
6. **Deployment** — Render (backend) + Vercel (frontend)
7. **GitHub repo + README**
8. **Design decisions document** (written at end of project)

---

## UI design (finalized — do not change)

### Colors
- Page background: `#111`
- Card surfaces: `#191919`
- Primary accent: `#1D9E75` (teal)
- Hover: `#22b585`
- Borders: `#252525` default / `#2e2e2e` focus
- Section labels: `#777`
- Placeholder text: `#444`

### Typography
- **DM Sans** (300/400/500) — all UI chrome
- **DM Mono** (400/500) — section labels, uppercase + letter-spacing
- **Lora italic** — textarea and ask input text only

### Behavior
- Button disabled until input has content
- Thinking dots animation while `/ask` is in-flight
- Enter key submits ask
- Result cards: green tint = saved, dark = coach response, red tint = error
- Fade-up animation on result cards
- Native fetch (no axios)

---

## Hard rules
1. No LangChain, no LlamaIndex. All RAG implemented manually.
2. The frontend is Create React App — do not migrate to Vite.
3. Don't change the UI design language.
4. At end of project, produce a full design decisions document.