"""
lead-gen-tool  •  STEP 2: the worker.

Run it by hand:   python worker.py poll

It connects to the Supabase `runs` table, finds queued jobs, and walks each
one through its lifecycle:  queued -> running -> done  (or -> failed on error).

This is the HAPPY-PATH version. It does not yet recover from a worker that
dies mid-job -- that's Step 5, and we'll watch it break first.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# .strip() defends against stray whitespace/newlines in .env or CI secrets,
# which otherwise cause a confusing "Invalid URL" only in the cloud.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    sys.exit("Missing SUPABASE_URL / SUPABASE_SERVICE_KEY. Did you fill in .env?")

db = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# A job 'running' longer than this is assumed dead (its worker crashed) and
# gets reset to 'queued'. In production this is ~30 min (1800s); it's an env
# var so the demo can use a small value. Must be longer than the slowest real
# job, or we'd reclaim jobs that are still legitimately working.
STALE_SECONDS = int(os.environ.get("STALE_SECONDS", "1800"))


def do_work(run):
    """
    The slow, failure-prone work. In the real tool this is where you'd call a
    scraping API and collect leads. Here we just sleep to simulate it.
    """
    print(f"  ...working on {run['trade']} in {run['city']} (a few seconds)")
    time.sleep(3)
    return 12  # pretend we found 12 leads


def reconcile():
    """
    Self-healing step: reclaim jobs whose worker died mid-run.

    Any row stuck in 'running' past STALE_SECONDS is assumed dead and reset to
    'queued' so it gets retried on this same poll. This is why 'updated_at' has
    to be accurate -- the DB trigger stamps it on every status change, and we
    measure staleness against it.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_SECONDS)).isoformat()
    stale = (
        db.table("runs")
        .select("id")
        .eq("status", "running")
        .lt("updated_at", cutoff)
        .execute()
        .data
    )
    for row in stale:
        db.table("runs").update({"status": "queued"}).eq("id", row["id"]).execute()
        print(f"Run {row['id']}: stale 'running' -> 'queued' (recovered a dead job)")


def poll(crash=False):
    """Find queued jobs (oldest first) and process each one."""
    # Heal first: put any dead jobs back on the queue before we look for work.
    reconcile()

    runs = (
        db.table("runs")
        .select("*")
        .eq("status", "queued")
        .order("created_at")
        .execute()
        .data
    )

    if not runs:
        print("No queued runs.")
        return

    for run in runs:
        run_id = run["id"]

        # Claim it: queued -> running, so a second worker won't grab the same job.
        db.table("runs").update({"status": "running"}).eq("id", run_id).execute()
        print(f"Run {run_id}: queued -> running")

        # Simulate the runner being KILLED mid-job (timeout / hang / cancel).
        # The process just dies -- it never marks the job done, so the row is
        # left stranded in 'running' forever.
        if crash:
            print(f"Run {run_id}: 💥 worker killed mid-job!")
            os._exit(1)

        try:
            found = do_work(run)
            db.table("runs").update({"status": "done"}).eq("id", run_id).execute()
            print(f"Run {run_id}: running -> done ({found} leads)")
        except Exception as exc:
            # Any error -> mark the job failed with the reason, and keep going.
            db.table("runs").update(
                {"status": "failed"}
            ).eq("id", run_id).execute()
            print(f"Run {run_id}: running -> failed ({exc})")


def enqueue(city, trade):
    """Convenience for testing (the real UI does this in Step 4)."""
    row = db.table("runs").insert({"city": city, "trade": trade}).execute().data[0]
    print(f"Enqueued run {row['id']}: {trade} in {city} [queued]")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "poll"
    if cmd == "poll":
        poll()
    elif cmd == "poll-crash":
        poll(crash=True)
    elif cmd == "enqueue":
        enqueue(sys.argv[2], sys.argv[3])
    else:
        print("commands: poll | enqueue <city> <trade>")
