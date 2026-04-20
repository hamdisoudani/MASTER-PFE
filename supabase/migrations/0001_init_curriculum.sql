-- 0001_init_curriculum.sql
-- Curriculum source of truth for MASTER-PFE.
-- Hierarchy: thread -> syllabus (1:1 per thread) -> chapters (1:N) -> lessons (1:N).
-- No RLS yet (single-tenant / no auth). Realtime is enabled so the frontend can subscribe.

create extension if not exists "pgcrypto";

-- ---------- syllabi ----------
create table if not exists public.syllabi (
    id          uuid primary key default gen_random_uuid(),
    thread_id   text not null unique,                 -- LangGraph thread id owns exactly one syllabus
    title       text not null default 'Untitled syllabus',
    description text,
    metadata    jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create index if not exists syllabi_thread_id_idx on public.syllabi (thread_id);

-- ---------- chapters ----------
create table if not exists public.chapters (
    id           uuid primary key default gen_random_uuid(),
    syllabus_id  uuid not null references public.syllabi(id) on delete cascade,
    position     int  not null,
    title        text not null,
    summary      text,
    metadata     jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (syllabus_id, position)
);
create index if not exists chapters_syllabus_id_idx on public.chapters (syllabus_id, position);

-- ---------- lessons ----------
create table if not exists public.lessons (
    id          uuid primary key default gen_random_uuid(),
    chapter_id  uuid not null references public.chapters(id) on delete cascade,
    position    int  not null,
    title       text not null,
    blocks      jsonb not null default '[]'::jsonb,    -- BlockNote block array
    block_count int  generated always as (jsonb_array_length(blocks)) stored,
    version     int  not null default 1,               -- optimistic concurrency
    last_author text,                                  -- 'writer' | 'reviser' | 'user'
    metadata    jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (chapter_id, position)
);
create index if not exists lessons_chapter_id_idx on public.lessons (chapter_id, position);

-- ---------- append-only audit log ----------
create table if not exists public.lesson_edits (
    id            bigserial primary key,
    lesson_id     uuid not null references public.lessons(id) on delete cascade,
    op            text not null,                       -- 'add'|'update'|'append'|'patch'
    patch         jsonb,
    from_version  int,
    to_version    int,
    author        text,
    created_at    timestamptz not null default now()
);
create index if not exists lesson_edits_lesson_id_idx on public.lesson_edits (lesson_id, created_at desc);

-- ---------- updated_at trigger ----------
create or replace function public.tg_set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at := now();
    return new;
end $$;

drop trigger if exists syllabi_set_updated_at on public.syllabi;
create trigger syllabi_set_updated_at before update on public.syllabi
    for each row execute function public.tg_set_updated_at();

drop trigger if exists chapters_set_updated_at on public.chapters;
create trigger chapters_set_updated_at before update on public.chapters
    for each row execute function public.tg_set_updated_at();

drop trigger if exists lessons_set_updated_at on public.lessons;
create trigger lessons_set_updated_at before update on public.lessons
    for each row execute function public.tg_set_updated_at();

-- ---------- version bump on lesson mutations ----------
create or replace function public.tg_bump_lesson_version()
returns trigger language plpgsql as $$
begin
    if new.blocks is distinct from old.blocks or new.title is distinct from old.title then
        new.version := coalesce(old.version, 1) + 1;
    end if;
    return new;
end $$;

drop trigger if exists lessons_bump_version on public.lessons;
create trigger lessons_bump_version before update on public.lessons
    for each row execute function public.tg_bump_lesson_version();

-- ---------- Realtime publication ----------
-- Publish all curriculum tables so the frontend can subscribe to postgres_changes.
do $$
begin
    if not exists (
        select 1 from pg_publication where pubname = 'supabase_realtime'
    ) then
        create publication supabase_realtime;
    end if;
end $$;

alter publication supabase_realtime add table public.syllabi;
alter publication supabase_realtime add table public.chapters;
alter publication supabase_realtime add table public.lessons;

-- Ensure REPLICA IDENTITY FULL so UPDATE/DELETE payloads include old row (nice for Realtime diff).
alter table public.syllabi  replica identity full;
alter table public.chapters replica identity full;
alter table public.lessons  replica identity full;

-- No RLS (single-tenant mode). Explicitly disable in case it was enabled elsewhere.
alter table public.syllabi   disable row level security;
alter table public.chapters  disable row level security;
alter table public.lessons   disable row level security;
alter table public.lesson_edits disable row level security;
