#!/usr/bin/env python3
"""
ig-term — Instagram DMs from your terminal.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from getpass import getpass

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError

SESSION_FILE = Path(__file__).parent / ".ig_session.json"
SETTINGS_FILE = Path(__file__).parent / ".ig_settings.json"


# ── Helpers ──────────────────────────────────────────────────────────

def _load_env():
    """Load .env if present."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def _get_client() -> Client:
    cl = Client()
    # Load saved session if it exists
    if SETTINGS_FILE.exists():
        cl.set_settings(json.loads(SETTINGS_FILE.read_text()))
        # Try a lightweight check — if it fails, we re-login
        try:
            cl.get_timeline_feed()
        except LoginRequired:
            pass  # will need login
        except Exception:
            pass
    return cl


def _save_client(cl: Client):
    SETTINGS_FILE.write_text(json.dumps(cl.get_settings(), indent=2))
    print(f"✓ Session saved to {SETTINGS_FILE}")


def _ensure_logged_in(cl: Client):
    """Try a cheap API call. If it fails, prompt login."""
    try:
        cl.get_timeline_feed()
        return
    except LoginRequired:
        pass
    except Exception:
        return  # might be ok, let it ride

    print("Session expired. Logging in again...")
    _do_login(cl)


def _do_login(cl: Client):
    username = os.environ.get("IG_USERNAME") or input("Instagram username: ").strip()
    password = os.environ.get("IG_PASSWORD") or getpass("Instagram password: ").strip()

    try:
        cl.login(username, password)
    except ClientError as e:
        if "challenge_required" in str(e).lower():
            code = input("Enter 2FA code sent to your phone/email: ").strip()
            cl.login(username, password, verification_code=code)
        else:
            print(f"Login failed: {e}")
            sys.exit(1)

    _save_client(cl)
    print("✓ Logged in.")


def _format_user(user) -> str:
    return f"{user.full_name or user.username} (@{user.username})"


# ── Commands ─────────────────────────────────────────────────────────

def cmd_login(args):
    """Authenticate with Instagram and save session."""
    cl = Client()
    _do_login(cl)


def cmd_threads(args):
    """List recent DM conversations."""
    cl = _get_client()
    _ensure_logged_in(cl)

    threads = cl.direct_threads(amount=args.limit or 20)
    if not threads:
        print("No conversations found.")
        return

    print(f"{'ID':<20} {'Participants':<40} {'Last msg':<50}")
    print("-" * 110)
    for t in threads:
        users = ", ".join(_format_user(u) for u in t.users)
        last_msg = ""
        if t.last_activity_at:
            # last_activity_at can be a timestamp
            pass
        preview = ""
        if t.items:
            item = t.items[0]
            preview = (item.text or "[media]")[:47]
        tid = t.id
        print(f"{tid:<20} {users:<40} {preview:<50}")


def cmd_read(args):
    """Read messages from a thread."""
    cl = _get_client()
    _ensure_logged_in(cl)

    thread_id = args.thread_id
    amount = args.limit or 30

    try:
        messages = cl.direct_messages(thread_id, amount=amount)
    except Exception as e:
        print(f"Error reading thread: {e}")
        sys.exit(1)

    if not messages:
        print("No messages in this thread.")
        return

    # Build a map of user_id -> username
    try:
        thread = cl.direct_thread(thread_id)
        user_map = {u.pk: _format_user(u) for u in thread.users}
    except Exception:
        user_map = {}

    print(f"\n── Thread {thread_id} ──\n")
    for msg in reversed(messages):
        sender = user_map.get(msg.user_id, f"user_{msg.user_id}")
        timestamp = msg.timestamp.strftime("%m-%d %H:%M") if msg.timestamp else ""
        text = msg.text or "[media/unsupported]"
        print(f"[{timestamp}] {sender}")
        print(f"  {text}")
        print()


def cmd_send(args):
    """Send a message to a thread."""
    cl = _get_client()
    _ensure_logged_in(cl)

    thread_id = args.thread_id
    text = args.text

    try:
        cl.direct_send(text, thread_ids=[thread_id])
        print(f"✓ Message sent to thread {thread_id}")
    except Exception as e:
        print(f"Error sending message: {e}")
        sys.exit(1)


def cmd_search(args):
    """Search for a user by username."""
    cl = _get_client()
    _ensure_logged_in(cl)

    try:
        user = cl.user_info_by_username(args.username)
        print(f"\n{_format_user(user)}")
        print(f"  PK:       {user.pk}")
        print(f"  Bio:      {user.biography or '(none)'}")
        print(f"  Followers: {user.follower_count}")
        print(f"  Following: {user.following_count}")
        print(f"  Private:  {user.is_private}")
    except Exception as e:
        print(f"User not found: {e}")
        sys.exit(1)


def cmd_start(args):
    """Start a new DM conversation with a user."""
    cl = _get_client()
    _ensure_logged_in(cl)

    try:
        user = cl.user_info_by_username(args.username)
        thread = cl.direct_send(args.text or "Hi!", user_ids=[user.pk])
        print(f"✓ Started conversation with {_format_user(user)}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


# ── CLI Entry ────────────────────────────────────────────────────────

def main():
    _load_env()

    parser = argparse.ArgumentParser(
        prog="ig-term",
        description="Instagram DMs from the terminal",
    )
    parser.add_argument("--limit", type=int, default=20, help="Limit results")

    sub = parser.add_subparsers(dest="command", required=True)

    # login
    sub.add_parser("login", help="Log in and save session")

    # threads
    sub.add_parser("threads", help="List recent DM threads")

    # read <thread_id>
    p_read = sub.add_parser("read", help="Read messages in a thread")
    p_read.add_argument("thread_id", help="Thread ID")
    p_read.add_argument("--limit", type=int, default=30, help="Max messages")

    # send <thread_id> <text>
    p_send = sub.add_parser("send", help="Send a message to a thread")
    p_send.add_argument("thread_id", help="Thread ID")
    p_send.add_argument("text", help="Message text")

    # search <username>
    p_search = sub.add_parser("search", help="Search for a user")
    p_search.add_argument("username", help="Instagram username")

    # start <username> [text]
    p_start = sub.add_parser("start", help="Start a new conversation")
    p_start.add_argument("username", help="Recipient username")
    p_start.add_argument("text", nargs="?", default="Hi!", help="First message")

    args = parser.parse_args()

    commands = {
        "login": cmd_login,
        "threads": cmd_threads,
        "read": cmd_read,
        "send": cmd_send,
        "search": cmd_search,
        "start": cmd_start,
    }

    commands[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
