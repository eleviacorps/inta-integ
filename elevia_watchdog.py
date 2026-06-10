#!/usr/bin/env python3
"""
elevia_watchdog.py — Polls dining room GC every 5 seconds for Elevia mentions.
When found: saves context to .elevia_pending.json and triggers hermes cron run.
Designed to run as a background process (terminal background=true).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(r"D:\Programming\ig-term")
os.chdir(PROJECT_DIR)

SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"
STATE_FILE = PROJECT_DIR / ".elevia_watchdog_state.json"
PENDING_FILE = PROJECT_DIR / ".elevia_pending.json"
THREAD_ID = "340282366841710301281152850720669272287"

sys.path.insert(0, str(PROJECT_DIR))
from instagrapi import Client

POLL_INTERVAL = 5  # seconds
FETCH_LIMIT = 15
CRON_JOB_ID = "e580770809a8"


def main():
    if not SETTINGS_FILE.exists():
        print("[WATCHDOG] No settings file found", flush=True)
        return

    cl = Client()
    cl.set_settings(json.loads(SETTINGS_FILE.read_text()))

    # Load state
    state = {"last_seen_id": "", "replied_ids": []}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    last_seen = state.get("last_seen_id", "")
    replied = set(state.get("replied_ids", []))
    me = str(cl.user_id)

    seed_done = bool(last_seen)

    print(f"[WATCHDOG] Started. Polling every {POLL_INTERVAL}s for Elevia mentions.", flush=True)

    while True:
        try:
            resp = cl.private_request(
                f"direct_v2/threads/{THREAD_ID}/",
                params={"limit": FETCH_LIMIT}
            )
            items = resp.get("thread", {}).get("items", [])
            if not items:
                time.sleep(POLL_INTERVAL)
                continue

            users = resp.get("thread", {}).get("users", [])
            user_map = {str(u.get("pk", "")): f"@{u.get('username','?')}" for u in users}
            newest_id = items[0].get("item_id", "")

            # First run: just seed last_seen, don't trigger
            if not seed_done:
                state["last_seen_id"] = newest_id
                STATE_FILE.write_text(json.dumps(state, indent=2))
                seed_done = True
                print(f"[WATCHDOG] Seeded at {newest_id}. Monitoring...", flush=True)
                time.sleep(POLL_INTERVAL)
                continue

            # Check for new messages
            if newest_id != last_seen:
                new_items = []
                seen_ids = set()
                for m in items:
                    mid = m.get("item_id", "")
                    if mid == last_seen:
                        break
                    if mid not in seen_ids:
                        new_items.append(m)
                        seen_ids.add(mid)

                if new_items:
                    context_lines = []
                    found_elevia = False
                    new_replied_ids = []

                    # Build full context from items (not just new items)
                    all_lines = []
                    for m in reversed(items):
                        mid = m.get("item_id", "")
                        uid = str(m.get("user_id", ""))
                        text = m.get("text", "") or "[media/video_call]"
                        sender = "you" if uid == me else user_map.get(uid, f"user_{uid}")
                        ts = m.get("timestamp", 0)
                        tstr = datetime.fromtimestamp(ts / 1_000_000).strftime("%H:%M")

                        is_new = mid in seen_ids or mid == newest_id
                        is_elevia = "elevia" in text.lower() or "elvia" in text.lower()

                        marker = ""
                        if is_new and uid != me and is_elevia and mid not in replied:
                            marker = " >>> ELEVIA >>>"
                            found_elevia = True
                            new_replied_ids.append(mid)

                        all_lines.append(f"[{tstr}] {sender}{marker}: {text[:250]}")

                    if found_elevia:
                        # Update last_seen
                        state["last_seen_id"] = newest_id
                        # Track replied IDs
                        updated_replied = replied | set(new_replied_ids)
                        state["replied_ids"] = list(updated_replied)[-200:]  # keep last 200
                        STATE_FILE.write_text(json.dumps(state, indent=2))

                        # Write pending context for the cron pre-run script
                        pending = {
                            "timestamp": datetime.now().isoformat(),
                            "context": all_lines,
                            "new_elevia_ids": new_replied_ids,
                        }
                        PENDING_FILE.write_text(json.dumps(pending, indent=2))

                        print(f"[WATCHDOG] Elevia mention detected! New IDs: {new_replied_ids}", flush=True)
                        print(f"[WATCHDOG] Triggering cron {CRON_JOB_ID}...", flush=True)

                        # Trigger the cron job
                        try:
                            result = subprocess.run(
                                ["hermes", "cron", "run", CRON_JOB_ID, "--accept-hooks"],
                                capture_output=True, text=True, timeout=15,
                                cwd=str(PROJECT_DIR)
                            )
                            if result.returncode == 0:
                                print(f"[WATCHDOG] Cron triggered: {result.stdout.strip()}", flush=True)
                            else:
                                print(f"[WATCHDOG] Cron trigger failed: {result.stderr.strip()}", flush=True)
                        except Exception as e:
                            print(f"[WATCHDOG] Cron trigger error: {e}", flush=True)
                    else:
                        # No Elevia mentions, just update last_seen
                        state["last_seen_id"] = newest_id
                        STATE_FILE.write_text(json.dumps(state, indent=2))

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("[WATCHDOG] Stopped.", flush=True)
            break
        except Exception as e:
            print(f"[WATCHDOG] Error: {e}", flush=True)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
