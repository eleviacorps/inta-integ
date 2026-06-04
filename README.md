# ig-term — Instagram DMs from your terminal

Built with instagrapi. Use Hermes or run directly.

## Setup

```bash
# Already done — venv exists
source .venv/Scripts/activate
```

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
# Edit .env with your Instagram username/password
```

## Usage

```bash
# First-time login (you'll be prompted for 2FA if needed)
python ig.py login

# List recent conversations
python ig.py threads

# Read messages from a thread (use the thread ID from threads list)
python ig.py read <thread_id>

# Send a message
python ig.py send <thread_id> "your message here"

# Search for a user by username
python ig.py search <username>

# Start a new conversation with someone
python ig.py start <username>
```

Session is saved automatically after login so you don't need to re-auth every time. If the session expires, just run `login` again.
