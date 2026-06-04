#!/usr/bin/env python3
"""
ig_live.py — Live Instagram DM watcher daemon.

Polls every 20 seconds and streams new messages in real-time.
Runs in the background, prints new DMs as they arrive.

Usage:
  python ig_live.py                    # Poll watched threads every 20s
  python ig_live.py --interval 10      # Poll every 10 seconds
  python ig_live.py --all              # Also show new inbox threads
"""
import json
import os
import sys
import time
import re
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent.resolve()
os.chdir(PROJECT_DIR)

SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"
STATE_FILE = PROJECT_DIR / ".ig_live_state.json"
THREADS_FILE = PROJECT_DIR / ".igt_threads.json"

from instagrapi import Client

# ── Auto-reply config ────────────────────────────────────────────────
AUTOREPLY_THREADS = {
    "340282366841710301244276166510740991224": {  # chandra / Shereen
        "match_patterns": [
            r"what (are|r) (you|u) (doing|up to|up\b)",
            r"wyd",
            r"whats up",
            r"wassup",
            r"wsp",
            r"where (are|r) (you|u)",
            r"u?busy",
            r"whatcha",
            r"what.*do(ing|in)",
        ],
        "reply": "am making breakfast",
    }
}


DEFAULT_WATCHED = {
    "dining room": "340282366841710301281152850720669272287",
    "chandra": "340282366841710301244276166510740991224",
}


def load_watched():
    watched = dict(DEFAULT_WATCHED)
    if THREADS_FILE.exists():
        watched.update(json.loads(THREADS_FILE.read_text()))
    return watched


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_seen": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fmt_time(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1_000_000).strftime("%H:%M:%S")
    except Exception:
        return ""


def check_thread(cl, name, thread_id, state):
    try:
        resp = cl.private_request(
            f"direct_v2/threads/{thread_id}/",
            params={"limit": 15},
        )
    except Exception as e:
        print(f"[DAEMON] ⚠ [{name}] {e}", flush=True)
        return

    items = resp.get("thread", {}).get("items", [])
    if not items:
        return

    users = resp.get("thread", {}).get("users", [])
    user_map = {str(u.get("pk", "")): f"@{u.get('username','?')}" for u in users}
    me = str(cl.user_id)

    last_seen_map = state.get("last_seen", {})
    last_seen = last_seen_map.get(thread_id, "")
    newest_id = items[0].get("item_id", "")

    if not last_seen:
        last_seen_map[thread_id] = newest_id
        save_state(state)
        return

    if newest_id == last_seen:
        return  # Nothing new

    # Collect messages we haven't seen (API returns newest-first)
    new_items = []
    for m in items:
        mid = m.get("item_id", "")
        if mid == last_seen:
            break
        new_items.append(m)

    if not new_items:
        last_seen_map[thread_id] = newest_id
        save_state(state)
        return

    # Check for auto-reply conditions first
    auto_config = AUTOREPLY_THREADS.get(thread_id)
    if auto_config:
        for m in new_items:
            uid = str(m.get("user_id", ""))
            if uid == me:
                continue
            text = (m.get("text", "") or "").strip().lower()
            for pat in auto_config["match_patterns"]:
                if re.search(pat, text):
                    reply_text = auto_config["reply"]
                    try:
                        cl.direct_send(reply_text, thread_ids=[thread_id])
                        print(f"\n🤖 Auto-replied to [{name}]: \"{reply_text}\"", flush=True)
                    except Exception as e:
                        print(f"[DAEMON] ⚠ [{name}] Auto-reply failed: {e}", flush=True)
                    break
            # Only check first message from them
            break

    # Print in chronological order
    for m in reversed(new_items):
        uid = str(m.get("user_id", ""))
        who = user_map.get(uid, f"user_{uid}")
        is_me = uid == me
        ts = fmt_time(m.get("timestamp", 0))
        text = m.get("text", "") or "[media/photo/video]"

        prefix = "📤" if is_me else "📥"
        sender = "you" if is_me else who
        print(f"\n{prefix} [{ts}] [{name}] {sender}", flush=True)
        print(f"   {text}", flush=True)

    last_seen_map[thread_id] = newest_id
    save_state(state)


def scan_inbox(cl):
    try:
        inbox = cl.private_request("direct_v2/inbox/", params={"limit": 20})
        return inbox.get("inbox", {}).get("threads", [])
    except Exception as e:
        print(f"[DAEMON] ⚠ Inbox scan: {e}", flush=True)
        return []


def main():
    interval = 20
    watch_all = False

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--interval" and i + 1 < len(args):
            interval = int(args[i + 1])
        elif arg == "--all":
            watch_all = True

    if not SETTINGS_FILE.exists():
        print("[DAEMON] ❌ No session. Run: python igt.py login", flush=True)
        sys.exit(1)

    cl = Client()
    cl.set_settings(json.loads(SETTINGS_FILE.read_text()))

    try:
        cl.get_timeline_feed()
    except Exception:
        print("[DAEMON] ❌ Session expired. Run: python igt.py login", flush=True)
        sys.exit(1)

    watched = load_watched()
    state = load_state()

    now = datetime.now().strftime("%H:%M:%S")
    print(f"🚀 IG Live @ {now} — polling every {interval}s", flush=True)

    seen_threads = set(watched.values())

    while True:
        try:
            for name, thread_id in watched.items():
                check_thread(cl, name, thread_id, state)

            if watch_all:
                threads = scan_inbox(cl)
                for t in threads:
                    tid = t.get("thread_id", "")
                    if tid not in seen_threads:
                        seen_threads.add(tid)
                        title = t.get("thread_title", "") or "(no title)"
                        users = t.get("users", [])
                        ulist = [u.get("username", "?") for u in users[:3]]
                        items = t.get("items", [])
                        preview = items[0].get("text", "")[:50] or "[media]" if items else ""
                        tag = "👥" if len(users) > 1 else " "
                        print(f"\n🆕 [{title}] {tag} @{', @'.join(ulist)}", flush=True)
                        print(f"   Last: {preview}", flush=True)

            time.sleep(interval)

        except KeyboardInterrupt:
            print("\n[DAEMON] 👋 Stopped.", flush=True)
            save_state(state)
            break
        except Exception as e:
            print(f"[DAEMON] ⚠ {e}", flush=True)
            time.sleep(interval)


if __name__ == "__main__":
    main()
