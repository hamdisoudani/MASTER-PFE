-- 0002_activities.sql
-- Adds the `activities` table (practice/assessment units under a chapter) plus
-- a mirror audit log `activity_edits`. An activity is a structured learning
-- object attached to a chapter: MCQ quiz, drill exercises, flashcards, or a
-- project brief. The kind-specific shape lives in `payload` (jsonb); the MCP
-- layer validates payload schemas per kind — the DB just guarantees integrity,
-- versioning, and realtime fanout.
--
-- DEV-SAFE: this migration drops any previous `activities` / `activity_edits`
-- from earlier iterations so re-running in a dev project cannot fail on a
-- partial / stale shape.

-- ---------- dev reset (safe: these objects only exist in later iterations) ----
drop table if exists public.activity_edits cascade;
drop table if exists public.activities     cascade;

-- ---------- activities ------------------------------------------------------
create table public.activities (
    id            uuid primary key default gen_random_uuid(),
    chapter_id    uuid not null references public.chapters(id) on delete cascade,
    position      int  not null,
    kind          text not null check (kind in ('mcq_quiz','drill_exercises','flashcards','project')),
    title         text not null,
    payload       jsonb not null default '{}'::jsonb,
    metadata      jsonb not null default '{}'::jsonb,
    version       int  not null default 1,
    last_author   text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (chapter_id, position)
);
create index activities_chapter_id_idx on public.activities (chapter_id, position);
create index activities_kind_idx       on public.activities (kind);

-- ---------- activity_edits (audit log, mirrors lesson_edits) ----------------
create table public.activity_edits (
    id            bigserial primary key,
    activity_id   uuid not null references public.activities(id) on delete cascade,
    op            text not null,                    -- 'add'|'patch'|'delete'
    patch         jsonb,
    from_version  int,
    to_version    int,
    author        text,
    created_at    timestamptz not null default now()
);
create index activity_edits_activity_id_idx on public.activity_edits (activity_id, created_at desc);

-- ---------- updated_at trigger (reuses function from 0001) ------------------
drop trigger if exists activities_set_updated_at on public.activities;
create trigger activities_set_updated_at before update on public.activities
    for each row execute function public.tg_set_updated_at();

-- ---------- version bump on activity mutation -------------------------------
create or replace function public.tg_bump_activity_version()
returns trigger language plpgsql as $$
begin
    if new.payload is distinct from old.payload
       or new.title is distinct from old.title
       or new.kind  is distinct from old.kind then
        new.version := coalesce(old.version, 1) + 1;
    end if;
    return new;
end $$;

drop trigger if exists activities_bump_version on public.activities;
create trigger activities_bump_version before update on public.activities
    for each row execute function public.tg_bump_activity_version();

-- ---------- Realtime publication -------------------------------------------
-- publication `supabase_realtime` already exists from 0001; just add the table.
do $$
begin
    if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
       and not exists (
           select 1 from pg_publication_tables
            where pubname='supabase_realtime'
              and schemaname='public' and tablename='activities'
       ) then
        alter publication supabase_realtime add table public.activities;
    end if;
end $$;

alter table public.activities      replica identity full;
alter table public.activity_edits  disable row level security;
alter table public.activities      disable row level security;
