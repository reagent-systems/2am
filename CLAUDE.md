# 2am — agentic system

## Architecture

Act-first loop. Worker acts, checker evaluates. Plan only as fallback when act fails.

```
worker.act() → checker.check() → done? → finish
                               ↓ continue
                          worker.act() again
                               ↓ failed
                          worker.plan() → subdivide / retry / wait / undo / share
                               ↓ subdivide
                          spawn child Worker+Checker pairs × N  (concurrent)
                          each child: worker.act() → checker.check()
                                                   ↓ complex output
                                              checker._subdivide_check()
                                              spawn sub-checkers × N  (concurrent)
                                              aggregate verdicts
                          inject child results into parent context → back to ACT
```

Depth is bounded: max_turns halves at each spawning level (20 → 10 → 5 → 3).
Waiting for a subagent to complete is also a valid action — agents loop until completion.


## Key files

| File | Purpose |
|------|---------|
| `main/main.py` | Agent class + `_run_pair()` loop + CLI entry point |
| `archive/tools/tools.py` | MCP tool server: spawn_agent, archive_search, archive_store, broadcast |
| `archive/tools/base_tools.json` | Tool definitions seeded into the vector DB on first run |
| `archive/db.py` | Vector DB (sparse TF cosine, JSON-backed, no external ML deps) |
| `archive/store.py` | Archive interface + agent config matching |
| `agents/worker/config/agent.yaml` | Canonical worker config (copied when spawning worker instances) |
| `agents/checker/config/agent.yaml` | Canonical checker config (copied when spawning checker instances) |
| `agents/running/` | Live agent instances (descriptive folder names like `searxng-search-worker`) |
| `messaging/bus.py` | Async pub/sub + broadcast log |

## Loop

`_run_pair(worker, checker)` drives the act-first loop:

1. Poll for `/btw` interrupts — mutate task if any
2. `worker.act()` — claude-agent-sdk query with MCP tools
3. `checker.check()` — quick API check, or subdivide into sub-checkers for complex output
4. Verdict:
   - `"done"` → exit loop, return result
   - `"continue"` → loop back to step 1 (no plan)
   - `"failed"` → `worker.plan()` → `_execute_plan()` (always returns None) → loop back to step 1

`_execute_plan()` never exits the loop. The only exit is checker saying `"done"` or hitting `max_turns`.

## Agent instances

Each agent lives in `agents/running/<slug>/`:
```
agents/running/searxng-search-worker/
  config/
    agent.yaml       # role, model, tools, system_prompt, task, parent
    pointers.yaml    # real archive IDs: skills, tools, knowledge, workflows
  workspace/         # working files
  context/sessions/  # session history
```

Slugs are descriptive: task words (stop words stripped) + role suffix.
`"search for news about AI"` + `"worker"` → `searxng-search-news-ai-worker`

## MCP tools (available to all agents)

Defined in `archive/tools/tools.py`, registered as an in-process MCP server.

| Tool | What it does |
|------|-------------|
| `spawn_agent` | Create a new agent instance, start Docker container (or subprocess fallback) |
| `archive_search` | Fuzzy search the vector DB for skills/tools/knowledge/agent configs |
| `archive_store` | Save a discovery (knowledge, skill, workflow) back to the archive |
| `broadcast` | Publish a message to the shared messaging bus |

## Archive types

Everything goes in one vector DB at `archive/data/`:

- `skill` — reusable capability description
- `tool` — tool definition with JSON schema
- `workflow` — multi-step process
- `knowledge` — anything agents discover
- `agent_config` — **config for spawning a new agent** (enables fuzzy task→agent matching)

```python
cfg = archive.get_agent_config("analyze a CSV file")
# returns the config for a data-analyst-like agent
```

## Running

```bash
pip install -r requirements.txt
python -m main.main --task "your task here"
# While running: type /btw <message> to interrupt
```

## Docker

```bash
AGENT_TASK="write a hello world script" docker-compose up root
```

## Adding agent configs to archive

```python
from archive.store import Archive
a = Archive()
a.add_agent_config(
    name="data_analyst",
    description="analyze data files, CSVs, run statistics, produce charts",
    config={
        "role": "worker",
        "tools": ["Read", "Bash", "Write"],
        "system_prompt": "You are a data analyst. Use pandas and matplotlib.",
    }
)
```
