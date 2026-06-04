#!/usr/bin/env python3
"""
Hermes helper for instagram operations via execute_code.
Import this to get fast, cached access:

    from ig_hermes import ig, threads, read, send
    
    # List threads
    t = threads()
    
    # Read a thread by name
    msgs = read("dining room")
    
    # Send a message
    send("chandra", "hey cutie")
    
    # Raw client for custom ops
    print(ig().user_id)

All functions auto-load the session (cached in memory per execute_code call).
"""

import json
import os
from pathlib import Path

PROJECT_DIR = Path(r"D:\Programming\ig-term")
SETTINGS_FILE = PROJECT_DIR / ".ig_settings.json"
THREADS_FILE = PROJECT_DIR / ".igt_threads.json"

from instagrapi import Client

# Module-level cache (persists during a single execute_code call)
_client = None
_threads = None


def ig():
    """Get a cached, authenticated Instagram client."""
    global _client
    if _client is not None:
        return _client
    _client = Client()
    _client.set_settings(json.loads(SETTINGS_FILE.read_text()))
    return _client


def _resolve(name):
    """Resolve friendly name to thread_id."""
    global _threads
    if _threads is None:
        _threads = {
            "dining room": "340282366841710301281152850720669272287",
            "chandra": "340282366841710301244276166510740991224",
        }
        if THREADS_FILE.exists():
            _threads.update(json.loads(THREADS_FILE.read_text()))

    name = name.lower().strip()
    if name in _threads:
        return _threads[name]
    for k, v in _threads.items():
        if name in k.lower():
            return v
    raise KeyError(f"No thread matching '{name}'")


def _fmt_user_map(resp):
    return {str(u.get("pk", "")): f"@{u.get('username','?')}" for u in resp.get("thread", {}).get("users", [])}


def threads():
    """List all known threads with their IDs."""
    global _threads
    if _threads is None:
        _resolve("")
    return dict(_threads)


def read(name, limit=20):
    """Read messages from a thread by name. Returns list of dicts."""
    c = ig()
    tid = _resolve(name)
    resp = c.private_request(f"direct_v2/threads/{tid}/", params={"limit": limit})
    items = resp.get("thread", {}).get("items", [])
    user_map = _fmt_user_map(resp)
    me = str(c.user_id)

    results = []
    for m in reversed(items):
        uid = str(m.get("user_id", ""))
        results.append({
            "sender": "you" if uid == me else user_map.get(uid, uid),
            "text": m.get("text", "") or "[media/video_call]",
            "timestamp": m.get("timestamp", 0),
        })
    return results


def send(name, text):
    """Send a message to a thread by name."""
    c = ig()
    tid = _resolve(name)
    c.direct_send(text, thread_ids=[tid])
    return {"status": "ok", "to": name, "sent": text[:80]}


def scan(limit=25):
    """Scan inbox for all threads. Returns list of {title, thread_id, users, preview}."""
    c = ig()
    inbox = c.private_request("direct_v2/inbox/", params={"limit": limit})
    threads_raw = inbox.get("inbox", {}).get("threads", [])
    results = []
    for t in threads_raw:
        items = t.get("items", [])
        preview = items[0].get("text", "")[:50] if items else ""
        if not preview and items:
            preview = "[media]"
        results.append({
            "title": t.get("thread_title", "") or "(no title)",
            "thread_id": t.get("thread_id", ""),
            "users": len(t.get("users", [])),
            "preview": preview,
        })
    return results
