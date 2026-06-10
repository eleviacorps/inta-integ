#!/usr/bin/env python3
"""
elevia_ping.py — Watches dining room GC for Elevia mentions.
Polls every 10s. Pings stdout when detected. NO auto-replies.
"""
import json, os, sys, time
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(r"D:\Programming\ig-term")
os.chdir(PROJECT_DIR)
SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"
STATE_FILE = PROJECT_DIR / ".elevia_ping.json"

sys.path.insert(0, str(PROJECT_DIR))
from instagrapi import Client

THREAD_ID = "340282366841710301281152850720669272287"

def main():
    if not SETTINGS_FILE.exists():
        return

    cl = Client()
    cl.set_settings(json.loads(SETTINGS_FILE.read_text()))
    try:
        cl.get_timeline_feed()
    except Exception:
        return

    state = {"last_seen": ""}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())

    me = str(cl.user_id)

    while True:
        try:
            resp = cl.private_request(f"direct_v2/threads/{THREAD_ID}/", params={"limit": 15})
            items = resp.get("thread", {}).get("items", [])
            if not items:
                time.sleep(10)
                continue

            users = resp.get("thread", {}).get("users", [])
            user_map = {str(u.get("pk", "")): f"@{u.get('username','?')}" for u in users}
            newest_id = items[0].get("item_id", "")
            last_seen = state.get("last_seen", "")

            if not last_seen:
                state["last_seen"] = newest_id
                STATE_FILE.write_text(json.dumps(state, indent=2))
                time.sleep(10)
                continue

            if newest_id != last_seen:
                new_items = []
                for m in items:
                    mid = m.get("item_id", "")
                    if mid == last_seen:
                        break
                    new_items.append(m)

                if new_items:
                    for m in reversed(new_items):
                        uid = str(m.get("user_id", ""))
                        text = m.get("text", "") or ""
                        sender = user_map.get(uid, "?")
                        if "elevia" in text.lower() or "elvia" in text.lower():
                            ts = datetime.now().strftime("%H:%M:%S")
                            print(f"\n⚡ ELEVIA PING [{ts}] {sender}: {text[:150]}\n", flush=True)

                    state["last_seen"] = newest_id
                    STATE_FILE.write_text(json.dumps(state, indent=2))

            time.sleep(10)

        except Exception:
            time.sleep(10)


if __name__ == "__main__":
    main()
