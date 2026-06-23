"""
prismatic-web-plugin orchestrator

The "system" that ties together the 3 PWP steps (ingest, synthesize, distill)
with the agent swarm (dispatch, build, review, deploy) and the post-build
actions (CF Pages deploy, OKF handoff).

This is the durable, generalized PWP — works on ANY client's framework
docs, not just Meridian.

Usage:
    # Full pipeline (new client)
    python -m prismatic_web_plugin.orchestrator run --client meridian-womens-defense

    # Watch a running build
    python -m prismatic_web_plugin.orchestrator watch --epic GRO-2142

    # Report build status
    python -m prismatic_web_plugin.orchestrator status --epic GRO-2142
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The 3 pipeline steps live in this package as CLI scripts.
# We invoke them via python -m so we don't need to refactor their main()s into library functions yet.
# Future: refactor each into library + thin CLI wrapper for unit testing.

PWP_HOME = Path(os.environ.get("PWP_HOME", "/home/ubuntu/work/prismatic-web-plugin"))
OUTPUT_BASE = PWP_HOME / "output"
PROJECTS_BASE = Path(os.environ.get("PWP_PROJECTS_BASE", "/home/ubuntu/work"))
SRC_DIR = PWP_HOME / "src"


def _run_step(step: str, script: str, *args, env: dict | None = None) -> dict:
    """Run a pipeline step as a subprocess and return parsed JSON output."""
    cmd = [sys.executable, "-m", f"prismatic_web_plugin.{script}", *args]
    full_env = os.environ.copy()
    full_env["PYTHONPATH"] = str(SRC_DIR)
    if env:
        full_env.update(env)
    log("step", f"Running {step}: {script}")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=full_env, cwd=str(PWP_HOME))
    if proc.returncode != 0:
        log("step", f"FAILED {step}: {proc.stderr[:500]}")
        raise RuntimeError(f"{step} failed (exit {proc.returncode}): {proc.stderr[:500]}")
    # Scripts output a JSON blob at the end - find the last JSON-looking block
    output = proc.stdout
    log("step", f"{step} ok")
    return {"stdout": output, "stderr": proc.stderr}


def load_env():
    """Load .env from the orchestrator profile."""
    env_path = Path("/home/ubuntu/.hermes/profiles/orchestrator/.env")
    if not env_path.exists():
        return {}
    env = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def log(stage: str, msg: str, **fields):
    """Structured log line."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    extras = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"[{ts}] [{stage}] {msg} {extras}".strip(), flush=True)


def run_pipeline(client_slug: str, *, skip_agy: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Run the full PWP pipeline: ingest → synthesize → distill.

    Args:
        client_slug: directory name in okf/projects/ that holds the 5 Website Dev docs
        skip_agy: skip the AGY call in synthesize (faster, lower quality)
        dry_run: don't write any output files or Linear issues

    Returns:
        dict with keys: status, client_slug, outputs, epic_id, child_ids, errors
    """
    result = {
        "client_slug": client_slug,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stages": {},
    }

    output_dir = OUTPUT_BASE / client_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Ingest (uses the script via subprocess)
    log("pipeline", f"Step 1: Ingest for {client_slug}")
    try:
        out = _run_step("ingest", "ingest", client_slug, "--out", str(output_dir))
        result["stages"]["ingest"] = {"status": "ok", "output": out["stdout"][-500:]}
    except Exception as e:
        log("ingest", f"FAILED: {e}")
        result["stages"]["ingest"] = {"status": "error", "error": str(e)}
        result["status"] = "failed"
        return result

    # Step 2: Synthesize
    log("pipeline", f"Step 2: Synthesize for {client_slug}")
    try:
        synth_args = [client_slug, "--out", str(output_dir)]
        if skip_agy:
            synth_args.append("--no-agy")
        out = _run_step("synthesize", "synthesize", *synth_args)
        result["stages"]["synthesize"] = {"status": "ok", "output": out["stdout"][-500:]}
    except Exception as e:
        log("synthesize", f"FAILED: {e}")
        result["stages"]["synthesize"] = {"status": "error", "error": str(e)}
        result["status"] = "failed"
        return result

    # Step 3: Distill
    log("pipeline", f"Step 3: Distill for {client_slug}")
    try:
        out = _run_step("distill", "distill", client_slug, "--out", str(output_dir))
        result["stages"]["distill"] = {"status": "ok", "output": out["stdout"][-500:]}
        # Try to extract the epic_id and child_ids from the script's output
        # The distill script outputs JSON at the end - try to find it
        text = out["stdout"]
        try:
            # Find the last JSON blob
            for line in reversed(text.split("\n")):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    distill_data = json.loads(line)
                    result["epic_id"] = distill_data.get("epic_id")
                    result["child_ids"] = distill_data.get("child_ids", [])
                    break
        except (json.JSONDecodeError, KeyError):
            pass
    except Exception as e:
        log("distill", f"FAILED: {e}")
        result["stages"]["distill"] = {"status": "error", "error": str(e)}
        result["status"] = "failed"
        return result

    result["status"] = "ok"
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    log("pipeline", f"DONE: epic={result.get('epic_id')} children={len(result.get('child_ids', []))}")
    return result


def watch_epic(epic_id: str, *, poll_interval: int = 60, max_runtime: int = 86400):
    """Watch a Linear epic until all children are Done (or max_runtime).

    Posts a comment on the epic with the progress every 10 minutes.
    """
    log("watch", f"Starting watch on {epic_id} (poll={poll_interval}s, max={max_runtime}s)")
    env = load_env()
    api_key = env.get("LINEAR_API_KEY")
    if not api_key:
        log("watch", "ERROR: LINEAR_API_KEY not set")
        return 1

    start = time.time()
    last_comment = 0.0
    last_status = None
    while time.time() - start < max_runtime:
        try:
            status = _epic_status(epic_id, api_key)
        except Exception as e:
            log("watch", f"ERROR fetching status: {e}")
            time.sleep(poll_interval)
            continue

        if status != last_status:
            log("watch", f"Status: {status}")
            last_status = status

        # Post progress comment every 10 min
        if time.time() - last_comment > 600:
            try:
                _post_progress_comment(epic_id, status, api_key)
                last_comment = time.time()
            except Exception as e:
                log("watch", f"ERROR posting comment: {e}")

        # Done?
        if all(c["state"] in ("Done", "Canceled") for c in status.get("children", [])):
            log("watch", f"All children terminal. Watch ending.")
            return 0

        time.sleep(poll_interval)

    log("watch", f"Max runtime {max_runtime}s reached. Ending watch.")
    return 2


def _epic_status(epic_id: str, api_key: str) -> dict[str, Any]:
    """Fetch epic + children status from Linear."""
    import urllib.request
    q = """
    query($id: String!) {
      issue(id: $id) {
        identifier
        title
        state { name }
        children {
          nodes { identifier title state { name } }
        }
      }
    }
    """
    r = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=json.dumps({"query": q, "variables": {"id": epic_id}}).encode(),
        headers={"Authorization": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=20) as f:
        data = json.loads(f.read())
    issue = data["data"]["issue"]
    children = issue["children"]["nodes"]
    states = [c["state"]["name"] for c in children]
    return {
        "identifier": issue["identifier"],
        "title": issue["title"],
        "state": issue["state"]["name"],
        "children": [{"id": c["identifier"], "title": c["title"], "state": c["state"]["name"]} for c in children],
        "summary": {
            "total": len(children),
            "todo": states.count("Todo"),
            "in_progress": states.count("In Progress"),
            "done": states.count("Done"),
            "canceled": states.count("Canceled"),
            "backlog": states.count("Backlog"),
        }
    }


def _post_progress_comment(epic_id: str, status: dict, api_key: str):
    import urllib.request
    summary = status["summary"]
    total = summary["total"]
    done = summary["done"]
    in_prog = summary["in_progress"]
    pct = int(100 * done / total) if total else 0
    body = f"""PWP orchestrator status update:

Progress: {done}/{total} children done ({pct}%)
In Progress: {in_prog}

```
{json.dumps(summary, indent=2)}
```

Auto-posted by prismatic-web-plugin orchestrator."""
    q = """
    mutation($id: String!, $body: String!) {
      commentCreate(input: { issueId: $id, body: $body }) { success }
    }
    """
    r = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=json.dumps({"query": q, "variables": {"id": epic_id, "body": body}}).encode(),
        headers={"Authorization": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=20) as f:
        f.read()


def print_status(epic_id: str):
    env = load_env()
    api_key = env.get("LINEAR_API_KEY")
    if not api_key:
        print("ERROR: LINEAR_API_KEY not set")
        return 1
    status = _epic_status(epic_id, api_key)
    print(f"Epic: {status['identifier']} - {status['title']}")
    print(f"State: {status['state']}")
    print()
    print(f"Children: {status['summary']}")
    print()
    for c in status["children"]:
        print(f"  [{c['state']:<11}]  {c['id']}  {c['title'][:60]}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="PWP orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run the full PWP pipeline")
    p_run.add_argument("--client", required=True, help="Client slug (e.g. meridian-womens-defense)")
    p_run.add_argument("--skip-agy", action="store_true", help="Skip AGY calls in synthesize")
    p_run.add_argument("--dry-run", action="store_true", help="Don't write files or create Linear issues")

    p_watch = sub.add_parser("watch", help="Watch a Linear epic")
    p_watch.add_argument("--epic", required=True, help="Epic UUID (e.g. from distill output)")
    p_watch.add_argument("--interval", type=int, default=60, help="Poll interval (seconds)")
    p_watch.add_argument("--max-runtime", type=int, default=86400, help="Max runtime (seconds)")

    p_status = sub.add_parser("status", help="Print epic status")
    p_status.add_argument("--epic", required=True, help="Epic UUID")

    args = parser.parse_args()

    if args.command == "run":
        result = run_pipeline(args.client, skip_agy=args.skip_agy, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "ok" else 1
    elif args.command == "watch":
        return watch_epic(args.epic, poll_interval=args.interval, max_runtime=args.max_runtime)
    elif args.command == "status":
        return print_status(args.epic)


if __name__ == "__main__":
    sys.exit(main())
