# 2am — agentic system

## Architecture

Act-first loop. Worker acts, checker evaluates. Plan only as fallback when act fails.
Agents replace themselves with workflows — automations that run without an agent loop.

```
worker.act() → checker.check() → done? → save_workflow? → finish
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


## Workflow lifecycle

Agents are not meant to run forever. When a task is repeatable, the agent encodes
it as a workflow and saves it to the archive. Future runs skip the agent loop entirely.

```
Before starting:
  archive_search(type="workflow") → found matching workflow?
    yes → run_workflow(name="...", inputs={...}) → done
    no  → proceed with agent loop as normal

After completing a repeatable task:
  save_workflow(name="...", description="...", steps=[...])
  → workflow saved to archive/workflows/<name>/workflow.yaml
  → future calls to run_workflow execute steps directly (no LLM, no agent session)
```

Workflows are deterministic step chains. Each step calls a tool's `execute()` function
directly. Variable interpolation: `{{ inputs.key }}` and `{{ steps.<id>.result }}`.


## Key files

| File | Purpose |
|------|---------|
| `main/main.py` | Agent class + `_run_pair()` loop + CLI entry point |
| `archive/tools/loader.py` | Discovers all tool.py files, builds MCP server per agent |
| `archive/tools/loader_seed.py` | Seeds tool READMEs into vector DB on first run |
| `archive/workflows/executor.py` | Runs a saved workflow step-by-step without an agent |
| `archive/workflows/loader.py` | Seeds workflow definitions into vector DB on first run |
| `archive/db/vector/__init__.py` | Vector DB (sparse TF cosine, JSON-backed) |
| `archive/db/vector/store.py` | Archive interface: add/search/list for all content types |
| `agents/worker/config/agent.yaml` | Canonical worker config (copied when spawning) |
| `agents/checker/config/agent.yaml` | Canonical checker config (copied when spawning) |
| `messaging/bus.py` | Async pub/sub + broadcast log |


## Loop

`_run_pair(worker, checker)` drives the Ralph Wiggum act-first loop:

1. Poll for `/btw` interrupts — mutate task if any
2. `worker.act()` — claude-agent-sdk query with all MCP tools
3. `checker.check()` — quick API check, or subdivide into sub-checkers for complex output
4. Verdict:
   - `"done"` → exit loop, return result
   - `"continue"` → loop back to step 1 (no plan)
   - `"failed"` → `worker.plan()` → `_execute_plan()` → loop back to step 1

`_execute_plan()` never exits the loop. The only exit is checker saying `"done"` or hitting `max_turns` (safety ceiling only — agents are expected to complete tasks).


## Agent instances

Each agent lives in `agents/<slug>/`:
```
agents/find-news-about-ai-worker/
  config/
    agent.yaml       # role, model, tools, system_prompt, task, parent
    pointers.yaml    # real archive IDs: skills, tools, knowledge, workflows
  workspace/         # working files
  context/sessions/  # session history
```

Slugs are descriptive: task words (stop words stripped) + role suffix.
`"search for news about AI"` + `"worker"` → `search-news-ai-worker`


## MCP tools (available to all agents)

Discovered from `archive/tools/*/tool.py`. Each exports `make_tool(archive, bus, parent_id)`.
Tools with `execute(args, archive, bus, parent_id)` can also be called from workflows.

| Tool | What it does |
|------|-------------|
| `spawn_agent` | Create a new agent instance, start Docker container (or subprocess fallback) |
| `archive_search` | Fuzzy search the vector DB for skills/tools/knowledge/workflows |
| `archive_store` | Save a discovery (knowledge, skill, tool, workflow) to the archive |
| `broadcast` | Publish a message to the shared messaging bus |
| `save_workflow` | Encode a completed automation as a reusable workflow |
| `run_workflow` | Execute a saved workflow directly (no agent loop, no LLM) |


## Workflows

Stored in `archive/workflows/<name>/`:
```
archive/workflows/fetch-ai-news/
  fetch-ai-news.py   # runnable Python script — primary artifact, no LLM
  workflow.yaml      # step metadata (source of truth / YAML fallback)
  description.md     # human-readable description
```

The Python script is generated by `save_workflow`. It calls tool `execute()` functions
directly and can be run standalone (`python archive/workflows/fetch-ai-news/fetch-ai-news.py`)
or invoked via `run_workflow`. Agents can edit it over time to optimise or extend.

The executor prefers the `.py` script; falls back to `workflow.yaml` step execution if absent.


## Archive types

Everything goes in one vector DB at `archive/data/`:

- `skill` — reusable capability description
- `tool` — tool definition with JSON schema
- `workflow` — multi-step automation (also has a file in `archive/workflows/`)
- `knowledge` — anything agents discover
- `agent_config` — config for spawning a new agent (enables fuzzy task→agent matching)


## Running

```bash
pip install -r requirements.txt
python -m main.main --task "your task here"
# While running: type /btw <message> to interrupt | /status to see agents
```

## Docker

```bash
AGENT_TASK="write a hello world script" docker-compose up root
```
