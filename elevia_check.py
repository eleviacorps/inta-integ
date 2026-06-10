#!/usr/bin/env python3
"""
elevia_check.py — Pre-run script for elevia-watch cron job.
Checks .elevia_pending.json (written by elevia_watchdog.py) for new Elevia mentions.
If found: outputs full GC context for the agent.
If not: reads the GC directly as fallback (but watchdog usually handles it).
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(r"D:\Programming\ig-term")
os.chdir(PROJECT_DIR)

SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"
STATE_FILE = PROJECT_DIR / ".elevia_replied.json"
PENDING_FILE = PROJECT_DIR / ".elevia_pending.json"
THREAD_ID = "340282366841710301281152850720669272287"

sys.path.insert(0, str(PROJECT_DIR))
from instagrapi import Client


def main():
    # --- CHECK WATCHDOG PENDING FILE FIRST ---
    if PENDING_FILE.exists():
        try:
            pending = json.loads(PENDING_FILE.read_text())
            PENDING_FILE.unlink()  # Clear it after reading
            context = pending.get("context", [])
            if context:
                print("--- DINING ROOM GC ---")
                for line in context:
                    print(line)
                print("---")
                print("Messages marked >>> ELEVIA >>> need a reply. Respond naturally, English only.")
                return
        except (json.JSONDecodeError, OSError):
            pass

    # --- FALLBACK: direct read if no pending file ---
    if not SETTINGS_FILE.exists():
        return

    cl = Client()
    cl.set_settings(json.loads(SETTINGS_FILE.read_text()))

    state = {"replied_ids": []}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    replied = set(state.get("replied_ids", []))

    resp = cl.private_request(f"direct_v2/threads/{THREAD_ID}/", params={"limit": 20})
    items = resp.get("thread", {}).get("items", [])
    if not items:
        return

    users = resp.get("thread", {}).get("users", [])
    user_map = {str(u.get("pk", "")): f"@{u.get('username','?')}" for u in users}
    me = str(cl.user_id)

    new_replied = set(replied)
    found_new = False
    all_lines = []

    for m in reversed(items):
        mid = m.get("item_id", "")
        uid = str(m.get("user_id", ""))
        text = m.get("text", "") or "[media/video_call]"
        sender = "you" if uid == me else user_map.get(uid, f"user_{uid}")
        ts = m.get("timestamp", 0)
        tstr = datetime.fromtimestamp(ts / 1_000_000).strftime("%H:%M")

        is_new_elevia = False
        if uid != me and mid not in replied:
            if "elevia" in text.lower() or "elvia" in text.lower():
                is_new_elevia = True
                found_new = True
                new_replied.add(mid)

        if uid == me:
            new_replied.add(mid)

        marker = " >>> ELEVIA >>>" if is_new_elevia else ""
        all_lines.append(f"[{tstr}] {sender}{marker}: {text[:250]}")

    if found_new:
        print("--- DINING ROOM GC ---")
        for line in all_lines:
            print(line)
        print("---")
        print("Messages marked >>> ELEVIA >>> need a reply. Respond naturally, English only.")

        state["replied_ids"] = list(new_replied)
        STATE_FILE.write_text(json.dumps(state, indent=2))

    # Trim stale IDs
    if len(new_replied) > 200:
        state["replied_ids"] = list(new_replied)[-150:]
        STATE_FILE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
