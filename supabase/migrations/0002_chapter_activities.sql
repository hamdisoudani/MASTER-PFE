-- 0002_chapter_activities.sql
-- Adds a generic "chapter activities" surface (starting with quizzes).
-- A chapter can own zero or more activities. Each activity stores a
-- typed JSON payload. For kind='quiz' the payload shape is:
--   {
--     "title": str,
--     "instructions": str?,
--     "questions": [
--        {
--          "id": str,
--          "prompt": str,
--          "kind": "single" | "multi" | "true_false",
--          "choices": [{"id": str, "text": str}],
--          "correct_choice_ids": [str, ...],  -- authoritative answer key
--          "explanation": str?
--        }, ...
--     ]
--   }
-- Correct answers live server-side. Verification is done frontend-side by
-- comparing selected choice ids to correct_choice_ids — cheap MVP that
-- lets us ship quizzes without a submissions API.

create table if not exists public.activities (
    id            uuid primary key default gen_random_uuid(),
    chapter_id    uuid not null references public.chapters(id) on delete cascade,
    position      int  not null,
    kind          text not null check (kind in ('quiz')),
    title         text not null,
    payload       jsonb not null default '{}'::jsonb,
    metadata      jsonb not null default '{}'::jsonb,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (chapter_id, position)
);
create index if not exists activities_chapter_id_idx
    on public.activities (chapter_id, position);

drop trigger if exists activities_set_updated_at on public.activities;
create trigger activities_set_updated_at before update on public.activities
    for each row execute function public.tg_set_updated_at();

alter publication supabase_realtime add table public.activities;
alter table public.activities replica identity full;
alter table public.activities disable row level security;
