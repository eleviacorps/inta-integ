"""Debug thread ID format for dining room."""
import json
from instagrapi import Client

cl = Client()
cl.set_settings(json.loads(open('.ig_settings.json').read()))

inbox = cl.private_request('direct_v2/inbox/', params={'limit': 20})
threads = inbox.get('inbox', {}).get('threads', [])

for t in threads:
    title = t.get('thread_title', '')
    if 'dining' not in title.lower():
        continue

    print("Thread keys:", list(t.keys()))
    print("thread_id:", t.get('thread_id'))
    print("thread_v2_id:", t.get('thread_v2_id'))

    tid = t.get('thread_id')
    try:
        resp = cl.private_request(f'direct_v2/threads/{tid}/')
        items = resp.get('thread', {}).get('items', [])
        print(f"Got {len(items)} messages via /threads/{{tid}}/")
        for m in items[:2]:
            print(json.dumps(m, indent=2)[:400])
    except Exception as e:
        print(f"direct_v2/threads/{tid}/ failed: {e}")

    # Try with just the numeric ID
    try:
        resp2 = cl.private_request(f'direct_v2/threads/{tid}/', params={'limit': 10})
        print("Works with limit param")
    except Exception as e:
        print(f"With limit param: {e}")

    break
