#!/usr/bin/env python3
"""
igt.py — Unified Instagram DM CLI with name resolution.

Usage:
  python igt.py scan              # Scan inbox, show all threads with names
  python igt.py threads           # Show watched/saved threads
  python igt.py read <name>       # Read messages (name or partial)
  python igt.py send <name> <msg> # Send a message
  python igt.py login             # Re-login if session expired
  python igt.py watch             # Add current thread to watch list
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent.resolve()
os.chdir(PROJECT_DIR)

SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"
THREADS_FILE = PROJECT_DIR / ".igt_threads.json"

from instagrapi import Client

# ── Default thread mappings (save/load from THREADS_FILE) ──────────
DEFAULT_THREADS = {
    "dining room": "340282366841710301281152850720669272287",
    "chandra": "340282366841710301244276166510740991224",
}


def load_threads():
    if THREADS_FILE.exists():
        merged = dict(DEFAULT_THREADS)
        merged.update(json.loads(THREADS_FILE.read_text()))
        return merged
    return dict(DEFAULT_THREADS)


def save_threads(threads):
    # Only save user-added ones, not defaults
    user = {k: v for k, v in threads.items() if k not in DEFAULT_THREADS}
    THREADS_FILE.write_text(json.dumps(user, indent=2))


def resolve_name(name, threads):
    """Match by exact name first, then partial."""
    name = name.lower().strip()
    if name in threads:
        return name, threads[name]
    # Partial match
    matches = [(k, v) for k in threads if name in k.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Multiple matches for '{name}':")
        for k, v in matches:
            print(f"  {k}")
        sys.exit(1)
    return None, None


# ── Client helpers ──────────────────────────────────────────────────

def get_client():
    cl = Client()
    cl.set_settings(json.loads(SETTINGS_FILE.read_text()))
    return cl


def ensure_session(cl):
    try:
        cl.get_timeline_feed()
    except Exception:
        print("Session expired. Run: python igt.py login", file=sys.stderr)
        sys.exit(1)


def fmt_user_map(resp):
    users = resp.get("thread", {}).get("users", [])
    return {str(u.get("pk", "")): f"@{u.get('username','?')}" for u in users}


def fmt_time(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1_000_000).strftime("%m-%d %H:%M")
    except Exception:
        return ""


# ── Commands ────────────────────────────────────────────────────────

def cmd_scan(cl):
    """Scan inbox and print all threads with titles."""
    inbox = cl.private_request("direct_v2/inbox/", params={"limit": 25})
    threads = inbox.get("inbox", {}).get("threads", [])
    watched = load_threads()

    print(f"{'TITLE':<30} {'USERS':<5} {'YOURS':<6} {'PREVIEW':<40}")
    print("-" * 85)
    for t in threads:
        title = t.get("thread_title", "") or "(no title)"
        tid = t.get("thread_id", "")
        users = len(t.get("users", []))
        items = t.get("items", [])
        preview = items[0].get("text", "")[:37] if items else ""
        if not preview and items:
            preview = "[media]"
        is_watched = "Watch" if tid in watched.values() else ""
        print(f"{title:<30} {users:<5} {is_watched:<6} {preview:<40}")


def cmd_threads(cl):
    """Show watched threads."""
    threads = load_threads()
    if not threads:
        print("No threads configured. Run `python igt.py scan` first.")
        return
    print(f"{'NAME':<25} {'THREAD ID':<50}")
    print("-" * 75)
    for name, tid in sorted(threads.items()):
        print(f"{name:<25} {tid:<50}")
    print(f"\n{len(threads)} threads tracked.")


def cmd_read(cl, name):
    """Read messages from a thread."""
    threads = load_threads()
    resolved, tid = resolve_name(name, threads)
    if not resolved:
        print(f"No thread matching '{name}'. Try `python igt.py scan` first.")
        sys.exit(1)

    resp = cl.private_request(f"direct_v2/threads/{tid}/")
    items = resp.get("thread", {}).get("items", [])
    user_map = fmt_user_map(resp)
    me = str(cl.user_id)

    if not items:
        print(f"[{resolved}] — no messages.")
        return

    print(f"\n{'─' * 50}")
    print(f"  {resolved}")
    print(f"{'─' * 50}")
    for m in reversed(items):
        uid = str(m.get("user_id", ""))
        who = user_map.get(uid, f"user_{uid}")
        if uid == me:
            who = "you"
        ts = fmt_time(m.get("timestamp", 0))
        text = m.get("text", "") or "[media/video_call]"
        print(f"  [{ts}] {who}: {text}")
    print()


def cmd_send(cl, name, text):
    """Send a message to a thread."""
    threads = load_threads()
    resolved, tid = resolve_name(name, threads)
    if not resolved:
        print(f"No thread matching '{name}'. Try `python igt.py scan` first.")
        sys.exit(1)

    cl.direct_send(text, thread_ids=[tid])
    print(f"✓ Sent to {resolved}: {text[:80]}")


def cmd_login(cl):
    """Login and save session."""
    from getpass import getpass
    username = os.environ.get("IG_USERNAME") or input("Instagram username: ").strip()
    password = os.environ.get("IG_PASSWORD") or getpass("Password: ").strip()
    try:
        cl.login(username, password)
    except Exception as e:
        if "challenge_required" in str(e).lower():
            code = input("2FA code: ").strip()
            cl.login(username, password, verification_code=code)
        else:
            print(f"Login failed: {e}")
            sys.exit(1)
    SETTINGS_FILE.write_text(json.dumps(cl.get_settings(), indent=2))
    print("✓ Logged in, session saved.")


def cmd_watch(cl):
    """Add threads from scan to watch list by matching name."""
    print("Usage: python igt.py watch <partial_name>")
    print("  First run `python igt.py scan` to see all threads.")
    print("  Then: `python igt.py watch dining`")
    sys.exit(1)


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    if not SETTINGS_FILE.exists() and len(sys.argv) > 1 and sys.argv[1] != "login":
        print("No session. First run: python igt.py login")
        sys.exit(1)

    cl = get_client() if (len(sys.argv) > 1 and sys.argv[1] != "login") else None
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    cmds = {
        "scan": lambda: cmd_scan(cl),
        "threads": lambda: cmd_threads(cl),
        "list": lambda: cmd_threads(cl),
        "read": lambda: cmd_read(cl, sys.argv[2] if len(sys.argv) > 2 else ""),
        "send": lambda: cmd_send(cl, sys.argv[2] if len(sys.argv) > 2 else "",
                               " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""),
        "login": lambda: cmd_login(Client()),
        "watch": lambda: cmd_watch(cl),
    }

    if not cmd or cmd == "-h" or cmd == "--help":
        print(__doc__)
        return

    if cmd not in cmds:
        print(f"Unknown command: {cmd}\n")
        print(__doc__)
        sys.exit(1)

    if cmd != "login":
        ensure_session(cl)

    try:
        cmds[cmd]()
    except IndexError:
        print(f"Usage: python igt.py {cmd} <name> [message]" if cmd == "send"
              else f"Usage: python igt.py {cmd} <name>")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
