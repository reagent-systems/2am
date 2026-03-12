"""
Telegram connector — bridges Telegram into the 2am message bus.

The user is treated as a participant on the bus, same as any agent.

Inbound (user → bus):
  Any message    → published to bus as type=task (agents see it and can act)
  /btw <agent> <msg> → published as type=interrupt to that agent
  File/photo     → saved to messaging/data/uploads/, reference published to bus

Outbound (bus → user):
  Tails broadcast.jsonl and forwards notable agent events to the chat.

Setup: see README.md
"""
import asyncio
import json
import os
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

BASE = Path(__file__).parent.parent.parent
INBOX = BASE / "messaging" / "data" / "inbox.jsonl"
BROADCAST = BASE / "messaging" / "data" / "broadcast.jsonl"
UPLOADS = BASE / "messaging" / "data" / "uploads"

# Only surface these statuses to the user (others are internal noise)
_SURFACE = {"pair_started", "pair_done", "acted", "planning", "spawning", "act_error", "sharing"}


def _write_inbox(msg: dict):
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    with open(INBOX, "a") as f:
        f.write(json.dumps(msg) + "\n")


async def _tail_broadcast(chat_id: int, app, since_pos: int, stop_event: asyncio.Event):
    """Forward notable bus events to the Telegram chat until stop_event is set."""
    pos = since_pos
    while not stop_event.is_set():
        await asyncio.sleep(2)
        if not BROADCAST.exists():
            continue
        with open(BROADCAST) as f:
            f.seek(pos)
            chunk = f.read()
            pos = f.tell()
        for line in chunk.strip().splitlines():
            if not line:
                continue
            try:
                content = json.loads(line).get("content", {})
                if not isinstance(content, dict):
                    continue
                status = content.get("status", "")
                if status not in _SURFACE:
                    continue
                agent = content.get("agent", content.get("worker", "?"))
                feedback = content.get("feedback", content.get("message", ""))
                if status == "pair_done":
                    output = content.get("output", "")
                    done = content.get("done", False)
                    text = f"✓ {agent} done\n\n{output[:4000]}" if done and output else f"⚠ {agent} ended without completing."
                    await app.bot.send_message(chat_id, text)
                    stop_event.set()
                else:
                    text = f"[{agent}] {status}"
                    if feedback:
                        text += f" — {feedback[:200]}"
                    await app.bot.send_message(chat_id, text)
            except json.JSONDecodeError:
                pass


# --- handlers ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Any plain text → task on the bus."""
    content = update.message.text
    sender = f"telegram:{update.effective_user.username or update.effective_user.id}"
    _write_inbox({"from": sender, "type": "task", "content": content})
    await update.message.reply_text(f"On the bus: {content[:80]}")

    # Start tailing the broadcast so the user sees agent activity
    pos = BROADCAST.stat().st_size if BROADCAST.exists() else 0
    stop = asyncio.Event()
    asyncio.create_task(_tail_broadcast(update.effective_chat.id, context.application, pos, stop))


async def handle_btw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/btw <agent> <message> — interrupt a specific agent."""
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /btw <agent-id> <message>")
        return
    agent, message = args[0], " ".join(args[1:])
    sender = f"telegram:{update.effective_user.username or update.effective_user.id}"
    _write_inbox({"from": sender, "type": "interrupt", "agent": agent, "content": message})
    await update.message.reply_text(f"Interrupt sent to {agent}.")


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — show latest agent statuses from the broadcast log."""
    if not BROADCAST.exists():
        await update.message.reply_text("No activity yet.")
        return
    agents: dict[str, dict] = {}
    for line in BROADCAST.read_text().strip().splitlines()[-200:]:
        try:
            c = json.loads(line).get("content", {})
            if isinstance(c, dict) and "agent" in c:
                agents[c["agent"]] = c
        except json.JSONDecodeError:
            pass
    if not agents:
        await update.message.reply_text("No agents active.")
        return
    lines = [
        f"{aid}: {info.get('status', '?')} — {info.get('feedback', info.get('message', ''))[:80]}"
        for aid, info in list(agents.items())[-10:]
    ]
    await update.message.reply_text("\n".join(lines))


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """File/photo → save to uploads/ and publish reference to bus."""
    UPLOADS.mkdir(parents=True, exist_ok=True)
    doc = update.message.document or (update.message.photo[-1] if update.message.photo else None)
    if not doc:
        return
    file = await doc.get_file()
    filename = getattr(doc, "file_name", None) or f"{doc.file_id}.jpg"
    dest = UPLOADS / filename
    await file.download_to_drive(dest)
    sender = f"telegram:{update.effective_user.username or update.effective_user.id}"
    _write_inbox({"from": sender, "type": "file", "content": str(dest), "filename": filename})
    await update.message.reply_text(f"File received: {filename}")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set — see messaging/telegram/README.md")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("btw", handle_btw))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("2am Telegram connector running. Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
