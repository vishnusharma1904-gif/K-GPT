-- ============================================================================
-- Migration 008 — Qwen 768-dim embeddings + shared institutional knowledge base
-- ----------------------------------------------------------------------------
-- Captures, as a version-controlled migration, the schema changes that the
-- 2026-06-24 session previously documented only as copy-paste SQL:
--   1. Move the pgvector store from its old width to 768 dims (Qwen embeddings,
--      Matryoshka-truncated). 768 stays under pgvector's 2000-dim index limit.
--   2. Add the shared/verified columns + match_shared_memory() used by the
--      admin-verified knowledge base feature.
-- All statements are idempotent / safe to re-run.
-- ============================================================================

-- 1) 768-dim vector store ----------------------------------------------------
drop index if exists idx_memory_embedding;
alter table memory_chunks drop column if exists embedding;
alter table memory_chunks add column embedding vector(768);
create index idx_memory_embedding on memory_chunks
  using ivfflat (embedding vector_cosine_ops) with (lists = 100);

drop function if exists match_memory(uuid, vector, int, float);
create function match_memory(
  p_user_id uuid, p_query vector(768),
  p_limit int default 6, p_min_sim float default 0.40
) returns table (id uuid, content text, source text, similarity float)
language sql stable as $$
  select m.id, m.content, m.source, 1 - (m.embedding <=> p_query) as similarity
  from memory_chunks m
  where m.user_id = p_user_id and m.embedding is not null
    and 1 - (m.embedding <=> p_query) >= p_min_sim
  order by m.embedding <=> p_query limit p_limit;
$$;

-- 2) Shared knowledge base ---------------------------------------------------
alter table memory_chunks add column if not exists shared   boolean not null default false;
alter table memory_chunks add column if not exists verified boolean not null default false;

-- Speeds up the institution-wide search (only a small slice of rows are shared).
create index if not exists idx_memory_shared on memory_chunks (shared) where shared = true;

create or replace function match_shared_memory(
  p_query vector(768), p_limit int default 6, p_min_sim float default 0.40
) returns table (id uuid, content text, source text, similarity float)
language sql stable as $$
  select m.id, m.content, m.source, 1 - (m.embedding <=> p_query) as similarity
  from memory_chunks m
  where m.shared = true and m.embedding is not null
    and 1 - (m.embedding <=> p_query) >= p_min_sim
  order by m.embedding <=> p_query limit p_limit;
$$;

-- 3) Reload PostgREST schema cache (always after DDL) ------------------------
notify pgrst, 'reload schema';
