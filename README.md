# 2am

An agentic system that loops until things are done.

Agents work in Worker + Checker pairs. The worker acts, the checker evaluates. If the checker says done, the loop exits. If it says failed, the worker plans — spawning subagents to handle blockers, waiting for results, then looping back to act. The only way out is the checker saying done.

---

## How it works

```
worker.act()
  └── checker.check()
        ├── done     → exit
        ├── continue → act again
        └── failed   → worker.plan()
                          ├── subdivide → spawn child Worker+Checker pairs (concurrent)
                          │               wait for results → inject into context → act again
                          ├── wait      → block on bus until specific agent finishes
                          ├── retry     → act again as-is
                          └── share/undo → adjust state → act again
```

Depth scales with complexity. Each spawned pair can spawn its own pairs. Checker pairs mirror worker pairs — complex outputs get broken into verification dimensions checked concurrently. Turn limits halve at each level (20 → 10 → 5 → 3).

---

## Project structure

```
agents/
  worker/           canonical worker config
  checker/          canonical checker config
  template/         blank agent template
  <slug>/           spawned instances live here alongside canonical configs

archive/
  db/
    __init__.py     VectorDB — sparse TF cosine, JSON-backed
    archive.py      Archive — typed interface (add_skill, get_agent_config, blend_configs)
  skills/
    web_research/   README.md
    code_writer/    README.md
    file_analyzer/  README.md
    task_decomposer/README.md
    data_processor/ README.md
    shell_executor/ README.md
    loader.py       seeds skills into the archive on first run
  tools/
    spawn_agent/    README.md  tool.py
    archive_search/ README.md  tool.py
    archive_store/  README.md  tool.py
    broadcast/      README.md  tool.py
    bash/           README.md
    web_search/     README.md
    searxng/        README.md
    loader.py       builds the MCP server from all tool.py files
    loader_seed.py  seeds tool descriptions into the archive on first run

messaging/
  bus.py            async pub/sub + broadcast log (JSONL-backed)

main/
  main.py           Agent class, _run_pair loop, CLI entry point
```

---

## Running

```bash
pip install -r requirements.txt
python -m main.main --task "your task here"
```

While running, type into stdin:
- `/btw <message>` — interrupt the agent with new context
- `/status` — print all agent statuses

---

## Agents

Each agent is a folder with a config, workspace, and context:

```
agents/find-news-about-ai-worker/
  config/
    agent.yaml      role, model, tools, system_prompt, task, parent
    pointers.yaml   archive IDs for relevant skills, tools, knowledge
  workspace/        working files
  context/sessions/ session history
```

Spawned agent names are derived from the task — stop words stripped, first 5 meaningful words hyphenated, role appended. `"find news about AI"` + `worker` → `find-news-ai-worker`.

---

## Archive

One vector DB for everything. Search returns the most relevant entries across all types:

| Type | What it holds |
|------|--------------|
| `skill` | reusable capability (how to do something) |
| `tool` | tool definition with description |
| `workflow` | multi-step process |
| `knowledge` | anything agents discover and store |
| `agent_config` | config for spawning a specific type of agent |

`agent_config` entries enable fuzzy task → agent matching:
```python
archive.get_agent_config("analyze a CSV file")
# returns the config closest to that description
```

---

## Adding a skill

Create `archive/skills/<name>/README.md`. It gets seeded into the archive automatically on next run.

## Adding a tool

Create `archive/tools/<name>/README.md` and `tool.py` with a `make_tool(archive, bus, parent_id)` function. The loader picks it up automatically.

---

## Docker

```bash
AGENT_TASK="write a hello world script" docker-compose up
```
