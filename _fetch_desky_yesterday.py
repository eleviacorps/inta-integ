#!/usr/bin/env python3
"""Fetch deskey120 messages from yesterday (June 8) via API pagination."""
import sys, json
sys.path.insert(0, ".")
from ig_hermes import ig
from datetime import datetime, timezone

cl = ig()
tid = "340282366841710301281152850720669272287"

# Yesterday's range
start_dt = datetime(2026, 6, 8, 0, 0, 0, tzinfo=timezone.utc)
end_dt = datetime(2026, 6, 9, 0, 0, 0, tzinfo=timezone.utc)
start_us = int(start_dt.timestamp() * 1000000)
end_us = int(end_dt.timestamp() * 1000000)

cursor = None
desky_msgs = []
for page in range(30):
    params = {"limit": 50}
    if cursor:
        params["cursor"] = cursor
        params["direction"] = "older"
    
    resp = cl.private_request(f"direct_v2/threads/{tid}/", params=params)
    items = resp.get("thread", {}).get("items", [])
    if not items:
        break
    
    user_map = {str(u.get("pk","")): u.get("username","?") for u in resp.get("thread", {}).get("users", [])}
    me = str(cl.user_id)
    
    for m in items:
        uid = str(m.get("user_id",""))
        username = "you" if uid == me else user_map.get(uid, uid)
        text = m.get("text","") or "[media]"
        ts = m.get("timestamp", 0)
        if "deskey120" in username.lower() and start_us <= ts < end_us:
            desky_msgs.append((ts, text))
    
    oldest_item = items[-1]
    oldest_ts = oldest_item.get("timestamp", 0)
    oldest_cursor = resp.get("thread", {}).get("oldest_cursor") or oldest_item.get("item_id", "")
    if not oldest_cursor or oldest_cursor == cursor:
        break
    cursor = oldest_cursor

desky_msgs.sort(key=lambda x: x[0])
print(f"Deskey messages from yesterday (June 8): {len(desky_msgs)}")
for ts, text in desky_msgs:
    tstr = datetime.fromtimestamp(ts/1000000, tz=timezone.utc).strftime("%H:%M")
    print(f"  [{tstr}] {text}")
