# Telegram connector

Bridges Telegram into the 2am message bus. The user joins the bus as a participant — the same bus all agents communicate on.

## How it works

```
User (Telegram) ──→ connector ──→ inbox.jsonl ──→ bus ──→ agents
                                                         ↓
User (Telegram) ←── connector ←── broadcast.jsonl ←─────┘
```

Messages flow both ways. Agents see what the user sends; the user sees what agents broadcast. Files sent via Telegram are saved to `messaging/data/uploads/` and published as file references on the bus.

## Setup

**1. Create a bot**

Message [@BotFather](https://t.me/BotFather) on Telegram:
```
/newbot
```
Copy the token it gives you.

**2. Add the token to your .env**

```
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
```

**3. Install dependencies**

```bash
pip install -r messaging/telegram/requirements.txt
```

**4. Run (alongside the main system)**

```bash
python -m messaging.telegram.connector
```

Run this in a separate terminal while the agent system is running.

## Usage

| What you send | What happens |
|---------------|-------------|
| Any text | Published to bus as a task — agents see it |
| `/btw <agent-id> <message>` | Interrupt a specific running agent |
| `/status` | Show latest agent statuses |
| File or photo | Saved to `messaging/data/uploads/`, reference published to bus |

You'll receive live updates as agents work: status changes, planning events, and final output when done.
