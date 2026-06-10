#!/usr/bin/env python3
"""
ig_live.py — Lightweight live DM watcher.

Uses inbox-level timestamp checks instead of reading full threads every tick.
Only fetches full thread messages when something actually changes.

Usage:
  python ig_live.py                    # Poll every 20s
  python ig_live.py --interval 10      # Faster
  python ig_live.py --all              # Also detect new inbox threads
"""
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent.resolve()
os.chdir(PROJECT_DIR)

SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"
STATE_FILE = PROJECT_DIR / ".ig_live_state.json"
THREADS_FILE = PROJECT_DIR / ".igt_threads.json"

from instagrapi import Client

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
    return {"last_seen": {}, "inbox_times": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fmt_time(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1_000_000).strftime("%H:%M:%S")
    except Exception:
        return ""


def check_inbox_light(cl, watched, state):
    """
    Lightweight check: hit inbox once, compare last_activity_at timestamps.
    Only fetch full threads for threads that have new activity.
    """
    try:
        inbox = cl.private_request("direct_v2/inbox/", params={"limit": 30})
        threads_raw = inbox.get("inbox", {}).get("threads", [])
    except Exception as e:
        print(f"[DAEMON] ⚠ Inbox check: {e}", flush=True)
        return

    # Map thread_id -> last_activity_at from inbox
    inbox_times = {}
    inbox_threads = {}
    for t in threads_raw:
        tid = t.get("thread_id", "")
        if tid:
            ts = t.get("last_activity_at", 0)
            inbox_times[tid] = ts
            inbox_threads[tid] = t

    # Compare with saved timestamps
    saved_times = state.get("inbox_times", {})
    changed = False
    changed_threads = set()

    # Check watched threads first
    watched_reverse = {v: k for k, v in watched.items()}
    for tid in watched.values():
        new_ts = inbox_times.get(tid, 0)
        old_ts = saved_times.get(tid, 0)
        if new_ts != old_ts:
            changed_threads.add(tid)
            changed = True

    # Also check for entirely new threads
    if "known_threads" not in state:
        state["known_threads"] = []
    known = set(state["known_threads"])
    watched_ids = set(watched.values())

    for tid in inbox_times:
        if tid not in known and tid not in watched_ids:
            known.add(tid)
            changed = True
            t = inbox_threads[tid]
            title = t.get("thread_title", "") or "(no title)"
            users = t.get("users", [])
            ulist = [u.get("username", "?") for u in users[:3]]
            tag = "👥" if len(users) > 1 else " "
            items = t.get("items", [])
            preview = items[0].get("text", "")[:60] or "[media]" if items else ""
            print(f"\n🆕 [{title}] {tag} @{', @'.join(ulist)}", flush=True)
            if preview:
                print(f"   Last: {preview}", flush=True)

    state["known_threads"] = list(known)

    # Only fetch full threads if something changed
    if changed:
        for tid in changed_threads:
            name = watched_reverse.get(tid, "unknown")
            try:
                resp = cl.private_request(f"direct_v2/threads/{tid}/", params={"limit": 10})
            except Exception as e:
                print(f"[DAEMON] ⚠ [{name}] {e}", flush=True)
                continue

            items = resp.get("thread", {}).get("items", [])
            if not items:
                continue

            users = resp.get("thread", {}).get("users", [])
            user_map = {str(u.get("pk", "")): f"@{u.get('username','?')}" for u in users}
            me = str(cl.user_id)

            last_seen_map = state.get("last_seen", {})
            last_seen = last_seen_map.get(tid, "")
            newest_id = items[0].get("item_id", "")

            if not last_seen:
                last_seen_map[tid] = newest_id
                save_state(state)
                continue

            if newest_id == last_seen:
                continue

            new_items = []
            for m in items:
                mid = m.get("item_id", "")
                if mid == last_seen:
                    break
                new_items.append(m)

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

            last_seen_map[tid] = newest_id

        # Update saved timestamps
        state["inbox_times"] = inbox_times
        save_state(state)


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
    print(f"🚀 IG Live @ {now} — polling every {interval}s (lightweight mode)", flush=True)

    while True:
        try:
            check_inbox_light(cl, watched, state)
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
