# Discord connector

Bridges Discord into the 2am message bus. The user joins the bus as a participant — the same bus all agents communicate on.

## How it works

```
User (Discord) ──→ connector ──→ inbox.jsonl ──→ bus ──→ agents
                                                        ↓
User (Discord) ←── connector ←── broadcast.jsonl ←─────┘
```

Messages you send in the watched channel go onto the bus. Agent broadcasts come back to that channel. File attachments are saved to `messaging/data/uploads/` and published as file references.

## Setup

### 1. Create a bot

Go to [discord.com/developers](https://discord.com/developers/applications):
- New Application → Bot → Reset Token → copy token
- Enable **Message Content Intent** under Privileged Gateway Intents
- Invite URL: OAuth2 → URL Generator → `bot` scope → `Send Messages`, `Read Message History`, `Add Reactions`

### 2. Get your channel ID

Right-click the channel → Copy Channel ID (enable Developer Mode in Discord settings first).

### 3. Add to your .env

```
DISCORD_BOT_TOKEN=your-token-here
DISCORD_CHANNEL_ID=123456789012345678
```

### 4. Install dependencies

```bash
pip install -r messaging/discord/requirements.txt
```

### 5. Run alongside the main system

```bash
python -m messaging.discord.connector
```

## Usage

| What you send | What happens |
|---------------|-------------|
| Any message in the channel | Published to bus as a task |
| `!btw <agent-id> <message>` | Interrupt a specific running agent |
| `!status` | Show latest agent statuses |
| File attachment | Saved to `messaging/data/uploads/`, reference published to bus |

The bot reacts with 👀 when it receives a task and 📎 when it receives a file.
