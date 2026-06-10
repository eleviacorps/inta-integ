#!/usr/bin/env python3
"""Jump back to yesterday's messages to find deskey120's messages."""
import sys, json
sys.path.insert(0, ".")
from ig_hermes import ig
from datetime import datetime, timezone

cl = ig()
tid = "340282366841710301281152850720669272287"

# June 8 23:59 UTC as starting point for yesterday
target_dt = datetime(2026, 6, 9, 0, 0, 0, tzinfo=timezone.utc)  # start of today
target_us = int(target_dt.timestamp() * 1000000)

cursor = None
found = []
for page in range(60):  # Go further back
    params = {"limit": 50}
    if cursor:
        params["cursor"] = cursor
        params["direction"] = "older"
    
    resp = cl.private_request(f"direct_v2/threads/{tid}/", params=params)
    items = resp.get("thread", {}).get("items", [])
    if not items:
        break
    
    um = {str(u.get("pk","")): u.get("username","?") for u in resp.get("thread", {}).get("users", [])}
    
    for m in items:
        uid = str(m.get("user_id",""))
        u = um.get(uid, uid)
        t = m.get("text","") or "[media]"
        ts = m.get("timestamp", 0)
        # Stop once we go past yesterday
        if ts < target_us - 86400*1000000:  # More than 1 day before today
            break
        if "deskey" in u.lower():
            found.append((ts, u, t))
    
    oldest_item = items[-1]
    oldest_ts = oldest_item.get("timestamp", 0)
    oldest_cursor = resp.get("thread", {}).get("oldest_cursor") or oldest_item.get("item_id", "")
    
    if not oldest_cursor or oldest_cursor == cursor:
        break
    cursor = oldest_cursor
    
    # Stop if we've gone past yesterday
    if oldest_ts < target_us - 86400*1000000:
        break

found.sort()
print(f"Deskey messages (including yesterday): {len(found)}")
for ts, u, t in found:
    dt_obj = datetime.fromtimestamp(ts/1000000, tz=timezone.utc)
    print(f"  [{dt_obj.strftime('%m-%d %H:%M')}] {u}: {t}")
