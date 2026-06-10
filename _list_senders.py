#!/usr/bin/env python3
"""List all unique senders in the dining room journals."""
import re, os

os.chdir("D:/Programming/ig-term")
files = [".journals/dining room/2026-06-08.txt", ".journals/dining room/2026-06-09.txt"]

all_senders = set()
for f in files:
    with open(f) as fh:
        for line in fh:
            m = re.search(r"\[@([^\]]+)\]", line)
            if m:
                all_senders.add(f"@{m.group(1)}")
            m2 = re.search(r"\[(user_\d+)\]", line)
            if m2:
                all_senders.add(m2.group(1))

for s in sorted(all_senders):
    print(s)
