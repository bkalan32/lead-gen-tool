"""
lead-gen-tool  •  STEP 4: the dashboard (UI).

Run it:   ./venv/bin/python app.py     then open http://localhost:5000

What it does (and what it deliberately does NOT do):
  - Lists every job and its status  (reads the queue)
  - "Add job" form enqueues a new job (writes a queued row)
  - "Run now" asks GitHub to fire the poll workflow immediately

It NEVER scrapes anything itself. It only touches the queue. That decoupling
is why a slow/failing worker can't freeze the UI.
"""
import json
import os
import urllib.request

from dotenv import load_dotenv
from flask import Flask, redirect, request
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
GH_DISPATCH_TOKEN = os.environ.get("GH_DISPATCH_TOKEN", "").strip()
GH_REPO = "bkalan32/lead-gen-tool"

db = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
app = Flask(__name__)

# status -> (background, text) colors for the badge
BADGE = {
    "queued":  ("#e5e7eb", "#374151"),
    "running": ("#dbeafe", "#1e40af"),
    "done":    ("#dcfce7", "#166534"),
    "failed":  ("#fee2e2", "#991b1b"),
}


def page(rows_html, notice=""):
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>lead-gen-tool</title>
<meta http-equiv="refresh" content="3">
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 16px; color:#111; }}
  h1 {{ font-size: 20px; }}
  form.inline {{ display:inline; }}
  input, button {{ font-size:14px; padding:6px 10px; }}
  table {{ width:100%; border-collapse:collapse; margin-top:16px; }}
  th, td {{ text-align:left; padding:8px; border-bottom:1px solid #eee; font-size:14px; }}
  .badge {{ padding:2px 8px; border-radius:999px; font-size:12px; font-weight:600; }}
  .bar {{ display:flex; gap:8px; align-items:center; margin:16px 0; }}
  .notice {{ background:#fef9c3; padding:8px 12px; border-radius:6px; font-size:13px; }}
</style></head>
<body>
  <h1>lead-gen-tool — job queue</h1>
  {f'<div class="notice">{notice}</div>' if notice else ''}
  <div class="bar">
    <form class="inline" method="post" action="/enqueue">
      <input name="city" placeholder="city" required>
      <input name="trade" placeholder="trade" required>
      <button type="submit">Add job</button>
    </form>
    <form class="inline" method="post" action="/run-now">
      <button type="submit">Run now</button>
    </form>
  </div>
  <table>
    <tr><th>#</th><th>trade</th><th>city</th><th>status</th><th>updated</th></tr>
    {rows_html}
  </table>
  <p style="color:#888;font-size:12px;">Auto-refreshes every 3s.</p>
</body></html>"""


@app.route("/")
def index():
    runs = (
        db.table("runs").select("*").order("created_at", desc=True).execute().data
    )
    rows = []
    for r in runs:
        bg, fg = BADGE.get(r["status"], ("#eee", "#333"))
        badge = f'<span class="badge" style="background:{bg};color:{fg}">{r["status"]}</span>'
        updated = (r["updated_at"] or "")[11:19]  # just HH:MM:SS
        rows.append(
            f"<tr><td>{r['id']}</td><td>{r['trade']}</td>"
            f"<td>{r['city']}</td><td>{badge}</td><td>{updated}</td></tr>"
        )
    return page("".join(rows) or "<tr><td colspan=5>(no jobs yet)</td></tr>")


@app.route("/enqueue", methods=["POST"])
def enqueue():
    db.table("runs").insert(
        {"city": request.form["city"], "trade": request.form["trade"]}
    ).execute()
    return redirect("/")


@app.route("/run-now", methods=["POST"])
def run_now():
    # Ask GitHub to fire the poll workflow immediately (workflow_dispatch).
    # GRACEFUL DEGRADATION: if no token is configured, we don't crash -- the
    # scheduled 10-min cron will still pick the job up. The trigger is just an
    # optimization on top of the queue, never a requirement.
    if not GH_DISPATCH_TOKEN:
        return page_notice("No GH_DISPATCH_TOKEN set — job will run on the next 10-min cron instead.")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GH_REPO}/actions/workflows/poll.yml/dispatches",
        data=json.dumps({"ref": "main"}).encode(),
        headers={
            "Authorization": f"Bearer {GH_DISPATCH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        return page_notice("Triggered a poll run on GitHub.")
    except Exception as exc:
        return page_notice(f"Couldn't trigger GitHub ({exc}) — cron will still pick it up.")


def page_notice(msg):
    runs = db.table("runs").select("*").order("created_at", desc=True).execute().data
    rows = []
    for r in runs:
        bg, fg = BADGE.get(r["status"], ("#eee", "#333"))
        badge = f'<span class="badge" style="background:{bg};color:{fg}">{r["status"]}</span>'
        rows.append(
            f"<tr><td>{r['id']}</td><td>{r['trade']}</td>"
            f"<td>{r['city']}</td><td>{badge}</td><td>{(r['updated_at'] or '')[11:19]}</td></tr>"
        )
    return page("".join(rows), notice=msg)


if __name__ == "__main__":
    # Not 5000 — macOS AirPlay Receiver squats on that port and returns 403.
    app.run(port=8000, debug=True)
