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

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    sys.exit("Missing SUPABASE_URL / SUPABASE_SERVICE_KEY. Did you fill in .env?")

db = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def do_work(run):
    """
    The slow, failure-prone work. In the real tool this is where you'd call a
    scraping API and collect leads. Here we just sleep to simulate it.
    """
    print(f"  ...working on {run['trade']} in {run['city']} (a few seconds)")
    time.sleep(3)
    return 12  # pretend we found 12 leads


def poll():
    """Find queued jobs (oldest first) and process each one."""
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
    elif cmd == "enqueue":
        enqueue(sys.argv[2], sys.argv[3])
    else:
        print("commands: poll | enqueue <city> <trade>")
