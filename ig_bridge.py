#!/usr/bin/env python3
"""
Hermes bridge for Instagram — call this from execute_code or terminal.
Returns JSON. Usage:

  python ig_bridge.py threads [--limit 20]
  python ig_bridge.py read <thread_id> [--limit 30]
  python ig_bridge.py send <thread_id> <text>
  python ig_bridge.py search <username>
  python ig_bridge.py start <username> [text]
  python ig_bridge.py login
"""

import json
import os
import sys
from pathlib import Path

# Make sure we're in the right dir
PROJECT_DIR = Path(__file__).parent.resolve()
os.chdir(PROJECT_DIR)

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError
from getpass import getpass

SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"


def _get_client() -> Client:
    cl = Client()
    if SETTINGS_FILE.exists():
        cl.set_settings(json.loads(SETTINGS_FILE.read_text()))
    return cl


def _ensure_logged_in(cl: Client):
    try:
        cl.get_timeline_feed()
        return
    except LoginRequired:
        pass
    _do_login(cl)


def _do_login(cl: Client):
    username = os.environ.get("IG_USERNAME") or input("Instagram username: ").strip()
    password = os.environ.get("IG_PASSWORD") or getpass("Instagram password: ").strip()
    try:
        cl.login(username, password)
    except ClientError as e:
        if "challenge_required" in str(e).lower():
            code = input("Enter 2FA code: ").strip()
            cl.login(username, password, verification_code=code)
        else:
            raise
    SETTINGS_FILE.write_text(json.dumps(cl.get_settings(), indent=2))
    print("Logged in and session saved.", file=sys.stderr)


def _fmt_user(u) -> str:
    return f"{u.full_name or u.username} (@{u.username})"


def _try_thread_users(cl, thread_id):
    try:
        thread = cl.direct_thread(thread_id)
        return {u.pk: _fmt_user(u) for u in thread.users}
    except Exception:
        return {}


def cmd_threads(cl, limit=20):
    _ensure_logged_in(cl)
    try:
        threads = cl.direct_threads(amount=limit)
    except Exception as e:
        # Fallback: use raw API if pydantic validation fails
        print(f"direct_threads() failed: {e}", file=sys.stderr)
        threads = _raw_threads(cl, limit)
    result = []
    for t in threads:
        users = [_fmt_user(u) for u in set(t.users)]
        preview = ""
        if t.items:
            item = t.items[0]
            preview = item.text or "[media]"
        result.append({
            "id": t.id,
            "users": users,
            "preview": preview[:100],
        })
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _raw_threads(cl, limit=20):
    """Fetch threads via raw API and build lightweight thread objects."""
    import datetime
    inbox = cl.private_request("direct_v2/inbox/", params={"limit": limit})
    threads_raw = inbox.get("inbox", {}).get("threads", [])
    results = []
    for t in threads_raw:
        users = []
        for u in t.get("users", []):
            name = u.get("full_name") or u.get("username", "?")
            uname = u.get("username", "?")
            users.append(f"{name} (@{uname})")
        items = t.get("items", [])
        preview = items[0].get("text", "") if items else ""
        if not preview and items:
            preview = "[media]"
        # Build a minimal thread-like object
        thread = type("RawThread", (), {
            "id": t["thread_id"],
            "users": [],
            "items": [],
        })()
        # We need to set users as User objects for _fmt_user
        # But we already formatted above. Let's just store strings.
        thread._users_str = users
        thread._preview = preview
        thread.id = t["thread_id"]
        # Create minimal User stubs so _ensure_logged_in loops don't crash
        class RawUser:
            pk = 0
            full_name = ""
            username = ""
            def __init__(self, d):
                self.pk = d.get("pk") or 0
                self.full_name = d.get("full_name") or ""
                self.username = d.get("username") or ""
        thread.users = [RawUser(u) for u in t.get("users", [])]
        # Create minimal Item stub
        class RawItem:
            text = ""
            def __init__(self, d):
                self.text = d.get("text") or ""
                self.id = d.get("item_id") or ""
                self.timestamp = None
                self.user_id = 0
        thread.items = []
        for item_data in items:
            ri = RawItem(item_data)
            ri.timestamp = datetime.datetime.fromtimestamp(
                item_data.get("timestamp", 0) / 1_000_000
            ) if item_data.get("timestamp") else None
            ri.user_id = item_data.get("user_id", 0)
            thread.items.append(ri)
        results.append(thread)
    return results


def cmd_read(cl, thread_id, limit=30):
    _ensure_logged_in(cl)
    msgs = cl.direct_messages(thread_id, amount=limit)
    user_map = _try_thread_users(cl, thread_id)
    result = []
    for m in reversed(msgs):
        result.append({
            "id": m.id,
            "user_id": m.user_id,
            "sender": user_map.get(m.user_id, str(m.user_id)),
            "timestamp": str(m.timestamp) if m.timestamp else "",
            "text": m.text or "[media/unsupported]",
        })
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_send(cl, thread_id, text):
    _ensure_logged_in(cl)
    cl.direct_send(text, thread_ids=[thread_id])
    print(json.dumps({"status": "ok", "thread_id": thread_id, "sent": text[:100]}, indent=2))


def cmd_search(cl, username):
    _ensure_logged_in(cl)
    u = cl.user_info_by_username(username)
    print(json.dumps({
        "pk": u.pk,
        "username": u.username,
        "full_name": u.full_name,
        "bio": u.biography or "",
        "followers": u.follower_count,
        "following": u.following_count,
        "private": u.is_private,
    }, indent=2, ensure_ascii=False))


def cmd_start(cl, username, text="Hi!"):
    _ensure_logged_in(cl)
    u = cl.user_info_by_username(username)
    cl.direct_send(text, user_ids=[u.pk])
    print(json.dumps({"status": "ok", "recipient": _fmt_user(u), "sent": text[:100]}, indent=2))


def cmd_login(cl):
    _do_login(cl)
    print(json.dumps({"status": "ok", "message": "Logged in"}))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["login", "threads", "read", "send", "search", "start"])
    parser.add_argument("args", nargs="*")
    parser.add_argument("--limit", type=int, default=20)
    opts = parser.parse_args()

    cl = _get_client()

    cmds = {
        "login": lambda: cmd_login(cl),
        "threads": lambda: cmd_threads(cl, opts.limit),
        "read": lambda: cmd_read(cl, opts.args[0], opts.limit if len(opts.args) < 2 else int(opts.args[1])),
        "send": lambda: cmd_send(cl, opts.args[0], opts.args[1]),
        "search": lambda: cmd_search(cl, opts.args[0]),
        "start": lambda: cmd_start(cl, opts.args[0], opts.args[1] if len(opts.args) > 1 else "Hi!"),
    }

    try:
        cmds[opts.command]()
    except IndexError:
        print(f"Error: missing argument for {opts.command}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
