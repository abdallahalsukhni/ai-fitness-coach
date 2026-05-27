-- ============================================================
-- AI Fitness Coach — Supabase setup  (run this in SQL Editor)
-- Safe to re-run: handles both fresh and pre-existing tables.
-- ============================================================

-- 1. Enable pgvector
create extension if not exists vector;

-- 2a. Drop the old table if it exists (we're in dev, no real data to lose)
drop table if exists workouts cascade;

-- 2b. Create workouts table fresh
--     embedding: 1024 dims to match Voyage AI voyage-3
create table workouts (
    id          bigserial     primary key,
    user_id     text          not null,
    raw_text    text          not null,
    chunk_text  text          not null,
    embedding   vector(1024)  not null,
    created_at  timestamptz   not null default now()
);

-- 3. IVFFlat index for fast cosine similarity search
create index workouts_embedding_idx
    on workouts
    using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- 4. Index on user_id for filtered queries
create index workouts_user_id_idx on workouts (user_id);

-- 5. match_workouts RPC — top N similar chunks for a user
create or replace function match_workouts(
    query_embedding  vector(1024),
    match_user_id    text,
    match_count      int     default 5,
    match_threshold  float   default 0.3
)
returns table (
    id          bigint,
    raw_text    text,
    chunk_text  text,
    created_at  timestamptz,
    similarity  float
)
language sql stable
as $$
    select
        w.id,
        w.raw_text,
        w.chunk_text,
        w.created_at,
        1 - (w.embedding <=> query_embedding) as similarity
    from workouts w
    where
        w.user_id = match_user_id
        and 1 - (w.embedding <=> query_embedding) > match_threshold
    order by w.embedding <=> query_embedding
    limit match_count;
$$;
