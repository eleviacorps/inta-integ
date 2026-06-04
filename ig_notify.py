#!/usr/bin/env python3
"""
ig_notify.py — Check watched DM threads for new messages.
Designed for cron: outputs nothing when quiet, prints alerts when new msgs appear.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent.resolve()
os.chdir(PROJECT_DIR)

SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"
STATE_FILE = PROJECT_DIR / ".ig_notify_state.json"

from instagrapi import Client

# ── Watched threads ─────────────────────────────────────────────────
# Add more: "friendly name": "thread_id"
WATCHED = {
    "dining room": "340282366841710301281152850720669272287",
}


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def check_thread(cl, name, thread_id, state):
    try:
        resp = cl.private_request(
            f"direct_v2/threads/{thread_id}/",
            params={"limit": 20},
        )
    except Exception as e:
        print(f"[{name}] API error: {e}", file=sys.stderr)
        return

    items = resp.get("thread", {}).get("items", [])
    if not items:
        return

    # Build user map
    users = resp.get("thread", {}).get("users", [])
    user_map = {str(u.get("pk", "")): u.get("username", "?") for u in users}

    last_seen = state.get(thread_id, "")
    newest_id = items[0].get("item_id", "")

    if not last_seen:
        # First run — just mark latest as seen
        state[thread_id] = newest_id
        return

    if newest_id == last_seen:
        return  # no new messages

    # Find new messages (older = later in list, they return newest-first)
    new_items = []
    for m in items:
        mid = m.get("item_id", "")
        if mid == last_seen:
            break
        new_items.append(m)

    if not new_items:
        state[thread_id] = newest_id
        return

    # Print alerts
    for m in reversed(new_items):
        uid = str(m.get("user_id", ""))
        user = user_map.get(uid, uid)
        ts = m.get("timestamp", 0)
        tstr = datetime.fromtimestamp(ts / 1_000_000).strftime("%H:%M")
        text = m.get("text", "") or "[media/video_call]"
        who = f"@{user}" if not user.isdigit() else f"user_{user}"
        print(f"[{name} @ {tstr}] {who}: {text}")

    state[thread_id] = newest_id


def main():
    if not SETTINGS_FILE.exists():
        print("No session file. Login first with `python ig.py login`.", file=sys.stderr)
        sys.exit(1)

    cl = Client()
    cl.set_settings(json.loads(SETTINGS_FILE.read_text()))

    # Verify session
    try:
        cl.get_timeline_feed()
    except Exception:
        print("Session expired. Please re-login with `python ig.py login`.", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    had_new = False

    for name, thread_id in WATCHED.items():
        check_thread(cl, name, thread_id, state)

    save_state(state)


if __name__ == "__main__":
    main()
