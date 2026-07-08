# lead-gen-tool

A lead-generation job pipeline, built in the correct order so the reliability
story is baked in from the start.

## Architecture (the one idea)

Nothing does work directly. **Work is a row in a queue.** A worker pulls rows
from the queue and processes them; a UI adds rows and reads their status. The
two never talk to each other — the queue is the only shared source of truth.

```
  UI / trigger  --->  [ runs table: queued -> running -> done/failed ]  <---  worker
   (adds rows)              (the queue / status board)                    (pulls rows)
                                        ^
                                        |
                                  scheduler (cron)
                                  wakes the worker
```

## Build order

1. **The job queue** — a `runs` table with a `status` state machine. ← *we are here*
2. **The worker** — claims a queued job, does the work, marks it done/failed.
3. **The scheduler** — runs the worker automatically on a timer.
4. **The UI / trigger** — adds jobs and shows their status.
5. **Hardening** — stuck-job recovery, timeouts, retries, cost caps.

## Step 1 — set up the queue

The schema lives in [`db/schema.sql`](db/schema.sql). Run it against your
database to create the `runs` table. See that file's comments for what each
column is for.
