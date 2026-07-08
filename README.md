# Bika Gift Bot

A two-session Telegram gift automation bot using Pyrogram user sessions.

## Command mapping

| Command | Session | Service |
|---|---:|---|
| `/cstart1` | 1 | Character Catcher |
| `/cstart2` | 2 | Character Catcher |
| `/sstart1` | 1 | SenpaiCatcher |
| `/sstart2` | 2 | SenpaiCatcher |

Session commands (owner-only, bot DM only):

```text
/connect1 <StringSession>
/connect2 <StringSession>
/clearss1
/clearss2
```

Gift start commands must be sent by an owner in the configured Gift Group as a reply to the recipient's message.

## Flow

1. The selected connected user account opens the selected catcher's DM.
2. It sends `/harem`.
3. It parses all IDs on the current page.
4. It clicks `Next` until no next-page button remains.
5. For each collected ID, the user account replies to the selected group message with `/gift <ID>`.
6. It waits for a confirmation message from the selected catcher bot and clicks the Confirm button.
7. Jobs are serialized per session slot. Session 1 and Session 2 can work independently.

## Setup

Recommended runtime for this package: Python 3.11 in a virtual environment.

```bash
cd bika-gift-bot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Edit `.env` and set at least:

```text
BOT_TOKEN=
API_ID=
API_HASH=
OWNER_IDS=123456789
MONGO_URI=mongodb+srv://...
DB_NAME=bika_gift_bot
SESSION_ENCRYPTION_KEY=...
GIFT_GROUP_ID=-1004294757492
```

The included `.env` already contains the requested catcher bot IDs and usernames. Replace the example encryption key before production if you have not stored sessions yet. Once sessions are stored, do not change the encryption key unless you clear/reconnect those sessions.

Run:

```bash
python app.py
```

PM2 example:

```bash
pm2 start app.py --name bika-gift-bot --interpreter .venv/bin/python
pm2 save
```

## Security notes

- `/connect1` and `/connect2` only work for configured owner IDs and only in the bot's private chat.
- The bot attempts to delete the `/connect...` message containing the StringSession.
- Session strings are encrypted with Fernet before MongoDB storage.
- Logs redact `/connect1` and `/connect2` arguments.
- Never share `.env`, MongoDB credentials, or StringSession values.

## MongoDB collections

- `user_sessions`: encrypted session slots and account metadata.
- `gift_jobs`: queued/running/completed/failed job history and progress.

## Important operational requirements

- The main bot must be able to read the owner commands in the Gift Group.
- Each connected user account must be able to message the target catcher bot and send messages in the Gift Group.
- The target bots' actual message/button wording must match the patterns implemented in `services/pagination.py` and `services/gift_service.py`.
- Character Catcher IDs are parsed from the clover marker (`☘️ 1234`).
- SenpaiCatcher IDs are parsed from the ID emoji (`🆔 1234`).
