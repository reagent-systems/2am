"""
Discord connector — bridges Discord into the 2am message bus.

The user joins the bus as a participant — same bus all agents communicate on.

Inbound (user → bus):
  Any message in watched channel  → published to bus as type=task
  !btw <agent> <message>          → interrupt to that agent
  !status                         → show agent statuses
  File attachment                 → saved to uploads/, reference on bus

Outbound (bus → user):
  Tails broadcast.jsonl and posts notable agent events to the channel.

Setup: see README.md
"""
import asyncio
import json
import os
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

BASE = Path(__file__).parent.parent.parent
INBOX = BASE / "messaging" / "data" / "inbox.jsonl"
BROADCAST = BASE / "messaging" / "data" / "broadcast.jsonl"
UPLOADS = BASE / "messaging" / "data" / "uploads"

_SURFACE = {"pair_started", "pair_done", "acted", "planning", "spawning", "act_error", "sharing"}


def _write_inbox(msg: dict):
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    with open(INBOX, "a") as f:
        f.write(json.dumps(msg) + "\n")


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Channel ID to forward bus broadcasts to (set via DISCORD_CHANNEL_ID env var)
_channel_id: int | None = None


@bot.event
async def on_ready():
    global _channel_id
    _channel_id = int(os.environ.get("DISCORD_CHANNEL_ID", 0)) or None
    print(f"2am Discord connector ready as {bot.user}")
    if _channel_id:
        bot.loop.create_task(_broadcast_to_discord())


async def _broadcast_to_discord():
    """Tail broadcast.jsonl and forward notable events to the Discord channel."""
    if not _channel_id:
        return
    channel = bot.get_channel(_channel_id)
    pos = BROADCAST.stat().st_size if BROADCAST.exists() else 0

    while True:
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
                    text = f"✓ **{agent}** done\n```\n{output[:1900]}\n```" if done and output else f"⚠ **{agent}** ended without completing."
                else:
                    text = f"`[{agent}]` {status}"
                    if feedback:
                        text += f" — {feedback[:200]}"
                if channel:
                    await channel.send(text)
            except json.JSONDecodeError:
                pass


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Handle file attachments first
    for attachment in message.attachments:
        UPLOADS.mkdir(parents=True, exist_ok=True)
        dest = UPLOADS / attachment.filename
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                dest.write_bytes(await resp.read())
        sender = f"discord:{message.author.name}"
        _write_inbox({"from": sender, "type": "file", "content": str(dest), "filename": attachment.filename})
        await message.add_reaction("📎")

    await bot.process_commands(message)


@bot.command(name="btw")
async def btw_cmd(ctx: commands.Context, agent: str, *, message: str):
    """!btw <agent-id> <message> — interrupt a running agent."""
    sender = f"discord:{ctx.author.name}"
    _write_inbox({"from": sender, "type": "interrupt", "agent": agent, "content": message})
    await ctx.message.add_reaction("✉️")


@bot.command(name="status")
async def status_cmd(ctx: commands.Context):
    """!status — show latest agent statuses."""
    if not BROADCAST.exists():
        await ctx.send("No activity yet.")
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
        await ctx.send("No agents active.")
        return
    lines = [
        f"`{aid}`: {info.get('status', '?')} — {info.get('feedback', info.get('message', ''))[:80]}"
        for aid, info in list(agents.items())[-10:]
    ]
    await ctx.send("\n".join(lines))


@bot.event
async def on_message_without_command(message: discord.Message):
    """Plain messages (not commands) → publish to bus as task."""
    if message.author.bot or message.content.startswith("!"):
        return
    sender = f"discord:{message.author.name}"
    _write_inbox({"from": sender, "type": "task", "content": message.content})
    await message.add_reaction("👀")


def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN not set — see messaging/discord/README.md")
    bot.run(token)


if __name__ == "__main__":
    main()
