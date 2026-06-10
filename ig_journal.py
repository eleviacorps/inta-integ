#!/usr/bin/env python3
"""
ig_journal.py — Extract a full day's messages from an Instagram thread.

Usage:
  python ig_journal.py chandra today                   # Today's messages
  python ig_journal.py chandra 2026-06-07              # Specific date
  python ig_journal.py chandra yesterday               # Yesterday
  python ig_journal.py chandra today --save            # Save to file
  python ig_journal.py chandra today --save --open     # Save + print
  python ig_journal.py chandra today --threads "dining room"  # Multiple threads

Output:
  - Prints a formatted daily journal to stdout
  - With --save, writes to .journals/<thread>/<date>.txt
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

PROJECT_DIR = Path(__file__).parent.resolve()
os.chdir(PROJECT_DIR)

SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"
THREADS_FILE = PROJECT_DIR / ".igt_threads.json"

from instagrapi import Client

# ── Thread registry ──────────────────────────────────────────────
DEFAULT_THREADS = {
    "dining room": "340282366841710301281152850720669272287",
    "chandra": "340282366841710301244276166510740991224",
}

def load_threads():
    merged = dict(DEFAULT_THREADS)
    if THREADS_FILE.exists():
        merged.update(json.loads(THREADS_FILE.read_text()))
    return merged

def resolve_name(name, threads):
    name = name.lower().strip()
    if name in threads:
        return name, threads[name]
    matches = [(k, v) for k, v in threads.items() if name in k.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Multiple matches for '{name}':")
        for k, _ in matches:
            print(f"  {k}")
        sys.exit(1)
    return None, None

# ── Client ───────────────────────────────────────────────────────
def get_client():
    cl = Client()
    cl.set_settings(json.loads(SETTINGS_FILE.read_text()))
    return cl

# ── Date parsing ─────────────────────────────────────────────────
def parse_date(text):
    """Parse 'today', 'yesterday', or 'YYYY-MM-DD' into (start, end) timestamps in microseconds."""
    tz = timezone.utc  # Instagram timestamps are in UTC
    text = text.lower().strip()

    if text == "today":
        d = datetime.now(tz).date()
    elif text == "yesterday":
        d = (datetime.now(tz) - timedelta(days=1)).date()
    else:
        try:
            d = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            print(f"Invalid date: {text}. Use 'today', 'yesterday', or YYYY-MM-DD.")
            sys.exit(1)

    start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    end = start + timedelta(days=1)
    # Convert to microseconds (Instagram uses microseconds)
    start_us = int(start.timestamp() * 1_000_000)
    end_us = int(end.timestamp() * 1_000_000)
    return start_us, end_us, d

# ── Fetch all messages in range ──────────────────────────────────
def fetch_messages(cl, thread_id, start_us, end_us, max_pages=500):
    """Fetch all messages in [start_us, end_us) using cursor pagination."""
    all_messages = []
    cursor = None
    pages = 0

    while pages < max_pages:
        pages += 1
        params = {"limit": 50}  # limit=100 breaks has_older flag on IG's API
        if cursor:
            params["cursor"] = cursor
            params["direction"] = "older"

        resp = cl.private_request(f"direct_v2/threads/{thread_id}/", params=params)
        thread = resp.get("thread", {})
        items = thread.get("items", [])

        if not items:
            print(f"  Page {pages}: empty response, stopping.")
            break

        # Collect messages within our date range
        batch_collected = 0
        for item in items:
            ts = item.get("timestamp", 0)
            if start_us <= ts < end_us:
                all_messages.append(item)
                batch_collected += 1

        # Check oldest and newest messages in this batch
        oldest_ts = items[-1].get("timestamp", 0)
        newest_ts = items[0].get("timestamp", 0)
        oldest_cursor = thread.get("oldest_cursor") or items[-1].get("item_id", "")

        from datetime import datetime as _dt
        oldest_str = _dt.fromtimestamp(oldest_ts / 1_000_000).strftime("%H:%M") if oldest_ts else "?"
        print(f"  Page {pages}: +{batch_collected} msgs (range ~{oldest_str} → older)")

        # If the NEWEST message in this batch is already before start,
        # everything in this batch is before our date range → stop
        if newest_ts < start_us:
            print(f"  Gone past target date, stopping.")
            break

        # If oldest message is older than our range, we might still have
        # some in-range messages at the newer end of the batch.
        # Only stop if the batch had NO in-range messages.
        if batch_collected == 0 and oldest_ts < start_us:
            print(f"  No more messages in range, stopping.")
            break

        # Cursor didn't advance → avoid infinite loop
        if not oldest_cursor or oldest_cursor == cursor:
            print(f"  Cursor stalled, stopping.")
            break

        cursor = oldest_cursor

    return all_messages

# ── User map ─────────────────────────────────────────────────────
def build_user_map(resp):
    users = resp.get("thread", {}).get("users", [])
    return {str(u.get("pk", "")): f"@{u.get('username', '?')}" for u in users}

# ── Format journal ───────────────────────────────────────────────
def fmt_time(ts):
    if not ts:
        return "??:??"
    try:
        return datetime.fromtimestamp(ts / 1_000_000).strftime("%H:%M")
    except Exception:
        return "??:??"

def format_journal(messages, user_map, cl_user_id, thread_title, date_str):
    """Format messages into a readable daily journal."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  {thread_title}")
    lines.append(f"  {date_str}")
    lines.append("=" * 60)
    lines.append("")

    if not messages:
        lines.append("  No messages this day.")
        lines.append("")
        return "\n".join(lines)

    me = str(cl_user_id)

    # Sort by timestamp ascending
    sorted_msgs = sorted(messages, key=lambda m: m.get("timestamp", 0))

    # Group by hour for section headers
    current_hour = None
    for m in sorted_msgs:
        ts = m.get("timestamp", 0)
        uid = str(m.get("user_id", ""))
        who = user_map.get(uid, f"user_{uid}")
        if uid == me:
            who = "you"
        text = m.get("text", "") or "[media/video_call]"

        # Hour header
        try:
            dt = datetime.fromtimestamp(ts / 1_000_000)
            hour_key = dt.strftime("%H:00")
            if hour_key != current_hour:
                current_hour = hour_key
                lines.append(f"  ─── {hour_key} ───")
                lines.append("")
        except Exception:
            pass

        time_str = fmt_time(ts)
        lines.append(f"  [{time_str}] {who}: {text}")

    lines.append("")
    lines.append(f"  ── {len(messages)} messages ──")
    lines.append("")
    return "\n".join(lines)

# ── Journal directory ────────────────────────────────────────────
JOURNAL_DIR = PROJECT_DIR / ".journals"

def save_journal(content, thread_name, date_obj):
    """Save journal to .journals/<thread>/<date>.txt"""
    date_str = date_obj.strftime("%Y-%m-%d")
    dir_path = JOURNAL_DIR / thread_name
    dir_path.mkdir(parents=True, exist_ok=True)
    filepath = dir_path / f"{date_str}.txt"
    filepath.write_text(content, encoding="utf-8")
    return filepath

# ── Main ─────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract daily Instagram journal")
    parser.add_argument("thread", help="Thread name (chandra, dining room, etc.)")
    parser.add_argument("date", nargs="?", default="today",
                        help="Date: today, yesterday, or YYYY-MM-DD (default: today)")
    parser.add_argument("--save", "-s", action="store_true", help="Save to .journals/")
    parser.add_argument("--open", "-o", action="store_true", help="Print journal (default: just print)")
    args = parser.parse_args()

    # Resolve thread
    threads = load_threads()
    resolved, tid = resolve_name(args.thread, threads)
    if not resolved:
        print(f"No thread matching '{args.thread}'")
        sys.exit(1)

    # Parse date
    start_us, end_us, date_obj = parse_date(args.date)
    date_str = date_obj.strftime("%Y-%m-%d")
    day_name = date_obj.strftime("%A")

    # Fetch
    cl = get_client()
    user_id = cl.user_id

    # Get thread info for title
    resp = cl.private_request(f"direct_v2/threads/{tid}/", params={"limit": 1})
    user_map = build_user_map(resp)
    thread_title = resp.get("thread", {}).get("thread_title", "") or resolved

    print(f"Fetching messages for {resolved} on {date_str} ({day_name})...")
    messages = fetch_messages(cl, tid, start_us, end_us)
    print(f"Found {len(messages)} messages.")

    # Format
    journal = format_journal(messages, user_map, user_id, thread_title, date_str)
    print()

    if args.save:
        filepath = save_journal(journal, resolved, date_obj)
        print(f"Saved: {filepath}")

    # Unless --open was specifically given, we already printed above
    # Re-design: always print, --save also saves to file
    print(journal)

if __name__ == "__main__":
    main()
