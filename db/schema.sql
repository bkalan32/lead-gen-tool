-- ============================================================
-- lead-gen-tool  •  STEP 1: the job queue (the status board)
-- ============================================================
-- One row = one unit of work. The `status` column is the single
-- source of truth for where that work is in its lifecycle:
--
--     queued  ->  running  ->  done
--                         \->  failed
--
-- Nothing does work directly. Work is a row. The worker and the UI
-- both just read/write this table -- they never talk to each other.
-- ============================================================

create table if not exists runs (
    id         bigint generated always as identity primary key,
    city       text        not null,
    trade      text        not null,
    status     text        not null default 'queued'
                           check (status in ('queued','running','done','failed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- The poller runs "find queued jobs, oldest first" on every tick.
-- This index makes that lookup instant instead of a full table scan.
create index if not exists runs_status_created_idx on runs (status, created_at);

-- Auto-stamp updated_at on every change, so we can never forget to.
-- Step 5 (stuck-job recovery) depends on updated_at being accurate.
create or replace function touch_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists runs_touch_updated_at on runs;
create trigger runs_touch_updated_at
    before update on runs
    for each row execute function touch_updated_at();
