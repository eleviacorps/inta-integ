#!/usr/bin/env python3
"""Fetch dining room GC messages from 2 AM today to now - microseconds fix."""
import sys, datetime, json

sys.path.insert(0, ".")
from ig_hermes import read

IST_OFFSET = datetime.timedelta(hours=5, minutes=30)

msgs = read("dining room", limit=200)

# These are MICROSECONDS (16 digits)
MICRO = 1_000_000

# Current time for cutoff
now_utc = datetime.datetime.now(datetime.timezone.utc)
today_ist = now_utc + IST_OFFSET
cutoff_ist = today_ist.replace(hour=2, minute=0, second=0, microsecond=0)
cutoff_utc = cutoff_ist - IST_OFFSET
cutoff_us = int(cutoff_utc.timestamp() * MICRO)

print(f"Current time (IST): {today_ist.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Cutoff (UTC): {cutoff_utc.isoformat()}")
print(f"Cutoff (microseconds): {cutoff_us}")
print(f"Total messages fetched: {len(msgs)}")
print()

filtered = []
for m in msgs:
    if m["timestamp"] >= cutoff_us:
        filtered.append(m)

if not filtered:
    print("No messages found in range. Here are all messages:")
    for m in msgs:
        ts = datetime.datetime.fromtimestamp(m["timestamp"] / MICRO, tz=datetime.timezone.utc)
        local_ts = ts + IST_OFFSET
        print(f"  [{local_ts.strftime('%m/%d %H:%M')}] {m['sender']}: {m['text'][:100]}")
    print(f"\nTotal: {len(msgs)} messages")
else:
    print(f"Messages from 2 AM IST today: {len(filtered)}")
    print("=" * 70)
    for m in filtered:
        ts = datetime.datetime.fromtimestamp(m["timestamp"] / MICRO, tz=datetime.timezone.utc)
        local_ts = ts + IST_OFFSET
        print(f"[{local_ts.strftime('%H:%M')}] {m['sender']}: {m['text']}")
    print("=" * 70)

# Save raw for analysis
with open("_gc_fetch.json", "w") as f:
    out = []
    for m in filtered:
        ts = datetime.datetime.fromtimestamp(m["timestamp"] / MICRO, tz=datetime.timezone.utc) + IST_OFFSET
        out.append({"ts": ts.strftime("%H:%M"), "sender": m["sender"], "text": m["text"]})
    json.dump(out, f, indent=2)
print(f"\nSaved {len(filtered)} messages")
