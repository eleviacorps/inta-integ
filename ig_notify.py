#!/usr/bin/env python3
"""
ig_notify.py — Check DMs for new messages + auto-reply.
Cron-friendly: quiet when nothing new, prints alerts when messages arrive.
Auto-replies to Shereen (chandra) if she asks what I'm doing.
"""
import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent.resolve()
os.chdir(PROJECT_DIR)

SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"
STATE_FILE = PROJECT_DIR / ".ig_notify_state.json"
THREADS_FILE = PROJECT_DIR / ".igt_threads.json"

from instagrapi import Client

DEFAULT_WATCHED = {
    "dining room": "340282366841710301281152850720669272287",
    "chandra": "340282366841710301244276166510740991224",
}

# ── Auto-reply config ────────────────────────────────────────────────
# Auto-reply to Shereen (chandra) when she asks what I'm doing
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


def check_thread(cl, name, thread_id, state):
    try:
        resp = cl.private_request(
            f"direct_v2/threads/{thread_id}/",
            params={"limit": 15},
        )
    except Exception as e:
        print(f"[{name}] API error: {e}", file=sys.stderr)
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
        return

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
    autoreplied = False
    auto_config = AUTOREPLY_THREADS.get(thread_id)
    if auto_config:
        for m in new_items:
            uid = str(m.get("user_id", ""))
            if uid == me:
                continue  # skip own messages for trigger
            text = (m.get("text", "") or "").strip().lower()
            for pat in auto_config["match_patterns"]:
                if re.search(pat, text):
                    reply_text = auto_config["reply"]
                    try:
                        cl.direct_send(reply_text, thread_ids=[thread_id])
                        print(f"🤖 Auto-replied to [{name}]: \"{reply_text}\"")
                        autoreplied = True
                    except Exception as e:
                        print(f"[{name}] Auto-reply failed: {e}", file=sys.stderr)
                    break
            if autoreplied:
                break

    # Print alerts for new messages (skip if we auto-replied — already reported)
    if not autoreplied:
        for m in reversed(new_items):
            uid = str(m.get("user_id", ""))
            who = user_map.get(uid, f"user_{uid}")
            if uid == me:
                continue
            ts = m.get("timestamp", 0)
            tstr = datetime.fromtimestamp(ts / 1_000_000).strftime("%H:%M")
            text = m.get("text", "") or "[media/video_call]"
            print(f"📩 [{name}] {who} @ {tstr}: {text}")

    last_seen_map[thread_id] = newest_id
    save_state(state)


def scan_inbox_new(cl, state):
    """Scan inbox for threads we haven't seen before."""
    try:
        inbox = cl.private_request("direct_v2/inbox/", params={"limit": 15})
        threads = inbox.get("inbox", {}).get("threads", [])
    except Exception:
        return

    known = set(state.get("known_threads", []))
    new_known = set(known)
    watched = load_watched()
    watched_ids = set(watched.values())

    found_any = False
    for t in threads:
        tid = t.get("thread_id", "")
        if not tid:
            continue
        new_known.add(tid)
        if tid in known or tid in watched_ids:
            continue
        title = t.get("thread_title", "") or "(no title)"
        users = t.get("users", [])
        ulist = [u.get("username", "?") for u in users[:3]]
        tag = "👥" if len(users) > 1 else " "
        items = t.get("items", [])
        preview = items[0].get("text", "")[:60] or "[media]" if items else ""
        print(f"🆕 New thread: [{title}] {tag} @{', @'.join(ulist)}")
        if preview:
            print(f"   {preview}")
        found_any = True

    if found_any:
        state["known_threads"] = list(new_known)
        save_state(state)


def main():
    if not SETTINGS_FILE.exists():
        print("No session. Run: python igt.py login", file=sys.stderr)
        sys.exit(1)

    cl = Client()
    cl.set_settings(json.loads(SETTINGS_FILE.read_text()))

    try:
        cl.get_timeline_feed()
    except Exception:
        print("Session expired. Re-login: python igt.py login", file=sys.stderr)
        sys.exit(1)

    watched = load_watched()
    state = load_state()

    for name, thread_id in watched.items():
        check_thread(cl, name, thread_id, state)

    scan_inbox_new(cl, state)


if __name__ == "__main__":
    main()
