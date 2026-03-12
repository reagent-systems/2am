"""
main.py — the single script that every agent runs, inside or outside Docker.

Each agent is defined by its folder in agents/:
  agents/worker/                  canonical worker config
  agents/checker/                 canonical checker config
  agents/find-news-about-ai-worker/  spawned instance (lives alongside canonical configs)

Usage:
  python -m main.main --agent-name worker --task "your task"
  python -m main.main --agent-name find-news-about-ai-worker

Or via env var (inside Docker):
  AGENT_NAME=find-news-about-ai-worker python -m main.main

THE LOOP (Ralph Wiggum style — loops until completion):

  loop forever:
      [/btw interrupt check]
      1. ACT   — run a claude-agent-sdk session with all tools available
                 valid actions: do work | spawn subagent | wait for subagent
      2. CHECK — checker evaluates the output
         "done"     → EXIT LOOP
         "continue" → loop back to ACT (no plan needed)
         "failed"   → PLAN
      3. PLAN (fallback, only on failed)
         subdivide → spawn Worker+Checker pairs, wait for results, inject context
         wait      → block on bus for specific agent completion
         retry/undo/share → adjust state
         loop back to ACT ← always

  max_turns is a safety ceiling only — not the target.
  Agents are expected to complete tasks, not hit turn limits.
"""
import argparse
import asyncio
import json
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
import yaml
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, SystemMessage

BASE = Path(__file__).parent.parent
AGENTS_DIR = BASE / "agents"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class AgentConfig:
    name: str
    role: str
    task: str
    model: str = "claude-opus-4-6"
    max_turns: int = 20
    tools: list[str] = field(default_factory=list)
    system_prompt: str = ""
    permission_mode: str = "acceptEdits"
    parent: str = ""
    archive_pointers: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, agent_name: str, task_override: str | None = None) -> "AgentConfig":
        """Load from agents/<name>/config/agent.yaml + pointers.yaml"""
        agent_dir = _agent_dir(agent_name)
        cfg = yaml.safe_load((agent_dir / "config" / "agent.yaml").read_text())

        ptrs_path = agent_dir / "config" / "pointers.yaml"
        ptrs = yaml.safe_load(ptrs_path.read_text()) if ptrs_path.exists() else {}
        pointer_ids = (
            [p["id"] for p in ptrs.get("skills", []) if "id" in p]
            + [p["id"] for p in ptrs.get("tools", []) if "id" in p]
            + [p["id"] for p in ptrs.get("knowledge", []) if "id" in p]
        )

        return cls(
            name=cfg.get("name", agent_name),
            role=cfg.get("role", "worker"),
            task=task_override or cfg.get("task", ""),
            model=cfg.get("model", "claude-opus-4-6"),
            max_turns=cfg.get("max_turns", 20),
            tools=cfg.get("tools", []),
            system_prompt=cfg.get("system_prompt", ""),
            permission_mode=cfg.get("permission_mode", "acceptEdits"),
            parent=cfg.get("parent", ""),
            archive_pointers=pointer_ids,
        )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Agent:
    """
    Generic agent — behaviour driven by role in config YAML, not Python subclassing.
    role=worker  → act() tries to complete the task
    role=checker → check() evaluates another agent's output
    Both use claude-agent-sdk; checker also uses direct Anthropic API for fast evals.
    """

    def __init__(self, config: AgentConfig, archive, bus):
        self.config = config
        self.archive = archive
        self.bus = bus
        self.workspace = _agent_dir(config.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._client = anthropic.Anthropic()

    # ---- act (worker behaviour) ----

    async def act(self) -> dict:
        """Run a claude-agent-sdk session for the current task."""
        from archive.tools.loader import create_agent_tools
        from claude_agent_sdk import AgentDefinition

        # Build system prompt augmented with live archive context
        context = self.archive.format_context(
            self.archive.search(self.config.task, k=4)
        )
        system = self.config.system_prompt
        if context:
            system += f"\n\nArchive context:\n{context}"

        mcp_server = create_agent_tools(self.archive, self.bus, self.config.name)

        # Subagent definitions — workers can spawn these via the built-in Agent tool
        subagent_defs = {
            "worker": AgentDefinition(
                description="A focused worker that completes a subtask using tools.",
                prompt=system,
                tools=self.config.tools or ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            ),
            "checker": AgentDefinition(
                description="Evaluates whether a subtask was completed correctly.",
                prompt="You are a checker. Evaluate the output and respond with JSON: {status, feedback}",
                tools=["Read", "Bash", "Glob"],
            ),
        }

        output_parts = []
        session_id = None
        result_subtype = None

        async for msg in query(
            prompt=self.config.task,
            options=ClaudeAgentOptions(
                cwd=str(self.workspace),
                allowed_tools=self.config.tools or ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                mcp_servers={f"2am-{self.config.name}": mcp_server},
                system_prompt=system,
                model=self.config.model,
                max_turns=self.config.max_turns,
                permission_mode=self.config.permission_mode,
                setting_sources=["project"],  # loads CLAUDE.md
                agents=subagent_defs,
                output_config={"effort": "high"},
            ),
        ):
            if isinstance(msg, ResultMessage):
                result_subtype = msg.subtype
                # session_id lives on ResultMessage for resumption
                session_id = getattr(msg, "session_id", None)
                if session_id:
                    (self.workspace / ".session_id").write_text(session_id)
                if msg.subtype == "success" and msg.result:
                    output_parts.append(msg.result)

        output = "\n".join(output_parts)
        success = result_subtype == "success"
        feedback = {
            "error_max_turns": "hit turn limit — consider subdividing",
            "error_max_budget_usd": "hit budget limit",
            "error_during_execution": "execution error",
        }.get(result_subtype or "", "no output produced" if not output else "")

        return {
            "success": success,
            "output": output,
            "action": "act",
            "done": False,
            "feedback": feedback,
            "session_id": session_id,
            "result_subtype": result_subtype,
        }

    # ---- check (checker behaviour) ----

    async def check(self, task: str, output: str) -> dict:
        """
        Evaluate whether the worker's output completes the task.
        Subdivides verification for complex outputs.
        """
        quick = await self._quick_check(task, output)
        if quick["status"] in ("done", "failed"):
            return quick

        # Deep-check: spawn sub-checkers for independent verification dimensions
        if len(output) >= 600 and self.config.max_turns >= 6:
            return await self._subdivide_check(task, output)

        return quick

    async def _quick_check(self, task: str, output: str) -> dict:
        # Direct API call — fast, no tool loop needed for simple evaluation
        response = self._client.messages.create(
            model=self.config.model,
            max_tokens=300,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},  # balanced for eval
            messages=[{"role": "user", "content": f"""Task: {task}

Worker output:
{output or "(none yet)"}

Reply ONLY with valid JSON:
{{"status": "done"|"continue"|"failed", "feedback": "<one sentence>"}}

done=fully complete, continue=progressing, failed=wrong direction"""}],
        )
        raw = next((b.text for b in response.content if b.type == "text"), "")
        return _parse_json(raw, default={"status": "continue", "feedback": "parse error"})

    async def _subdivide_check(self, task: str, output: str) -> dict:
        """Ask Claude for verification dimensions, spawn a sub-checker per dimension."""
        from archive.tools.loader import _populate_pointers, _slug
        import shutil

        dims = await self._get_dimensions(task, output)
        if not dims:
            return await self._quick_check(task, output)

        await self.bus.broadcast(
            {"agent": self.config.name, "status": "subdividing_check", "dimensions": dims},
            sender=self.config.name,
        )

        async def check_dim(dim: str) -> dict:
            sub_id = _slug(dim, "checker")
            sub_dir = AGENTS_DIR / sub_id
            base_dir = AGENTS_DIR / "checker"
            shutil.copytree(base_dir, sub_dir, dirs_exist_ok=True)
            cfg = yaml.safe_load((sub_dir / "config" / "agent.yaml").read_text())
            cfg["task"] = f"check: {dim}"
            cfg["parent"] = self.config.name
            cfg["name"] = sub_id
            cfg["max_turns"] = max(self.config.max_turns // 2, 3)
            (sub_dir / "config" / "agent.yaml").write_text(yaml.dump(cfg, allow_unicode=True))
            _populate_pointers(sub_dir, dim, self.archive)
            sub_agent = Agent(AgentConfig.load(sub_id), self.archive, self.bus)
            return await sub_agent._quick_check(dim, output)

        verdicts = await asyncio.gather(*[check_dim(d) for d in dims], return_exceptions=True)

        statuses, feedbacks = [], []
        for v in verdicts:
            if isinstance(v, Exception):
                statuses.append("failed"); feedbacks.append(str(v))
            else:
                statuses.append(v["status"]); feedbacks.append(v.get("feedback", ""))

        if all(s == "done" for s in statuses):
            return {"status": "done", "feedback": "All verification dimensions passed."}
        if any(s == "failed" for s in statuses):
            return {"status": "failed", "feedback": " | ".join(f for s, f in zip(statuses, feedbacks) if s == "failed")}
        return {"status": "continue", "feedback": " | ".join(feedbacks)}

    async def _get_dimensions(self, task: str, output: str) -> list[str]:
        response = self._client.messages.create(
            model=self.config.model,
            max_tokens=256,
            messages=[{"role": "user", "content": f"""Task: {task}
Output (first 800 chars): {output[:800]}

List 2-4 independent verification questions. Reply ONLY with a JSON array:
["question 1", "question 2", ...]"""}],
        )
        raw = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(raw[raw.index("["):raw.rindex("]") + 1])[:4]
        except (ValueError, json.JSONDecodeError):
            return []

    # ---- plan ----

    async def plan(self, feedback: str) -> dict:
        """Decide how to unblock. Returns {action, subtasks?, seconds?, ...}"""
        context = self.archive.format_context(self.archive.search(self.config.task, k=3))

        output_parts = []
        async for msg in query(
            prompt=f"""Task: {self.config.task}

What went wrong: {feedback}

Archive context:
{context}

Decide the next action. Reply ONLY with valid JSON:
{{
  "action": "subdivide"|"retry"|"wait"|"undo"|"share",
  "reasoning": "<one sentence>",
  "subtasks": ["<subtask 1>", ...],
  "agent_id": "<agent-id-to-wait-for>",
  "seconds": 5,
  "data": "<content>"
}}

Use "wait" with "agent_id" to block until a specific spawned subagent completes.
Use "subdivide" to spawn new Worker+Checker pairs for blocking subtasks.""",
            options=ClaudeAgentOptions(
                cwd=str(self.workspace),
                allowed_tools=[],
                model=self.config.model,
                max_turns=3,
                permission_mode="default",
            ),
        ):
            if isinstance(msg, ResultMessage) and msg.result:
                output_parts.append(msg.result)

        raw = "\n".join(output_parts)
        plan = _parse_json(raw, default={"action": "retry", "reasoning": "parse error"})
        await self.bus.broadcast({"agent": self.config.name, "plan": plan, "status": "planning"}, sender=self.config.name)
        return plan

    # ---- plan execution (always returns — loop continues to act) ----

    async def _execute_plan(self, plan: dict) -> None:
        action = plan.get("action", "retry")

        if action == "subdivide":
            await self._subdivide(plan.get("subtasks", []))
        elif action == "wait":
            # Wait for a specific subagent to complete (by agent_id on bus)
            # or fall back to a timed sleep
            agent_id = plan.get("agent_id")
            secs = plan.get("seconds", 5)
            await self.bus.broadcast({"agent": self.config.name, "status": "waiting",
                                      "for": agent_id or f"{secs}s"}, sender=self.config.name)
            if agent_id:
                await _wait_for_agent(self.bus, agent_id, timeout=secs * 20)
            else:
                await asyncio.sleep(secs)
        elif action == "share":
            await self.bus.broadcast({"agent": self.config.name, "status": "sharing", "data": plan.get("data")}, sender=self.config.name)
        elif action == "undo":
            await self.bus.broadcast({"agent": self.config.name, "status": "undoing"}, sender=self.config.name)
        # retry/unknown → noop, loop returns to act

        await self.bus.broadcast({"agent": self.config.name, "status": "plan_done", "action": action}, sender=self.config.name)

    async def _subdivide(self, subtasks: list[str]) -> None:
        """Spawn Worker+Checker pairs for blocker subtasks. Inject results into task context."""
        from archive.tools.loader import _populate_pointers, _slug
        import shutil

        await self.bus.broadcast({"agent": self.config.name, "status": "spawning", "subtasks": subtasks}, sender=self.config.name)

        async def run_subtask(subtask: str) -> dict:
            w_id = _slug(subtask, "worker")
            c_id = _slug(subtask, "checker")

            for role, slug in [("worker", w_id), ("checker", c_id)]:
                sub_dir = AGENTS_DIR / slug
                shutil.copytree(AGENTS_DIR / role, sub_dir, dirs_exist_ok=True)
                cfg = yaml.safe_load((sub_dir / "config" / "agent.yaml").read_text())
                cfg.update({"task": subtask, "parent": self.config.name, "name": slug,
                             "max_turns": max(self.config.max_turns // 2, 3)})
                (sub_dir / "config" / "agent.yaml").write_text(yaml.dump(cfg, allow_unicode=True))
                _populate_pointers(sub_dir, subtask, self.archive)

            w_cfg = AgentConfig.load(w_id)
            c_cfg = AgentConfig.load(c_id)
            worker = Agent(w_cfg, self.archive, self.bus)
            checker = Agent(c_cfg, self.archive, self.bus)
            return await _run_pair(worker, checker)

        results = await asyncio.gather(*[run_subtask(st) for st in subtasks], return_exceptions=True)

        summaries = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                summaries.append(f"[subtask {i+1} error: {r}]")
            elif r.get("output"):
                summaries.append(f"[subtask {i+1}]\n{r['output'][:600]}")
            else:
                summaries.append(f"[subtask {i+1}: done={r.get('done', False)}]")

        if summaries:
            self.config.task += "\n\n[Subagent results]\n" + "\n---\n".join(summaries)

        await self.bus.broadcast({"agent": self.config.name, "status": "subagents_done", "count": len(results)}, sender=self.config.name)

    def _save_context(self, data: dict):
        ctx = _agent_dir(self.config.name) / "context" / "sessions"
        ctx.mkdir(parents=True, exist_ok=True)
        (ctx / f"{self.config.name.replace('/', '_')}.json").write_text(
            json.dumps(data, indent=2, default=str)
        )


# ---------------------------------------------------------------------------
# _run_pair — canonical act-plan loop
# ---------------------------------------------------------------------------

async def _run_pair(worker: Agent, checker: Agent) -> dict:
    """
    Ralph Wiggum loop — runs until checker says "done".
    max_turns is a safety ceiling only; the checker is the only real exit.

    worker.act() → checker.check() → done? EXIT : continue? loop : failed? plan → loop
    """
    await worker.bus.broadcast(
        {"worker": worker.config.name, "checker": checker.config.name,
         "task": worker.config.task, "status": "pair_started"},
        sender=worker.config.name,
    )

    last_output = ""
    turn = 0

    while True:
        turn += 1

        # Safety ceiling — prevents runaway loops
        if turn > worker.config.max_turns:
            await worker.bus.broadcast(
                {"agent": worker.config.name, "status": "max_turns_hit", "turns": turn},
                sender=worker.config.name,
            )
            break

        # /btw interrupt
        if msg := worker.bus.poll_interrupt(worker.config.name):
            await worker.bus.broadcast({"agent": worker.config.name, "interrupt": msg}, sender=worker.config.name)
            worker.config.task += f"\n\n/btw: {msg}"

        # 1. ACT
        try:
            result = await worker.act()
        except Exception as e:
            await worker.bus.broadcast({"agent": worker.config.name, "error": str(e), "status": "act_error", "turn": turn}, sender=worker.config.name)
            break

        last_output = result.get("output", last_output)
        await worker.bus.broadcast({"worker": worker.config.name, "turn": turn, "status": "acted"}, sender=worker.config.name)

        # 2. CHECK
        try:
            verdict = await checker.check(worker.config.task, last_output)
        except Exception as e:
            verdict = {"status": "continue", "feedback": f"checker error: {e}"}

        await worker.bus.broadcast(
            {"worker": worker.config.name, "checker": checker.config.name,
             "verdict": verdict["status"], "feedback": verdict.get("feedback", ""), "turn": turn, "status": "checked"},
            sender=checker.config.name,
        )

        # Checker saying "done" is the only real exit
        if verdict["status"] == "done":
            worker._save_context({"done": True, "turns": turn, "output": last_output})
            await worker.bus.publish(worker.config.name,
                {"status": "pair_done", "done": True, "output": last_output},
                sender=worker.config.name)
            return {"done": True, "output": last_output, "agent": worker.config.name}

        if verdict["status"] == "continue":
            continue  # loop back to act, no plan needed

        # 3. PLAN (only on "failed")
        try:
            plan = await worker.plan(verdict["feedback"])
        except Exception as e:
            plan = {"action": "retry", "reasoning": str(e)}

        await worker._execute_plan(plan)
        # Always loop back to ACT after plan execution

    worker._save_context({"done": False, "turns": turn, "output": last_output})
    await worker.bus.publish(worker.config.name,
        {"status": "pair_done", "done": False, "output": last_output},
        sender=worker.config.name)
    return {"done": False, "output": last_output, "agent": worker.config.name}


async def _wait_for_agent(bus, agent_id: str, timeout: float = 120) -> dict | None:
    """Block until agent_id publishes a 'pair_done' status on the bus."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        msg = await bus.receive(agent_id, timeout=2.0)
        if msg:
            content = msg.get("content", {})
            if isinstance(content, dict) and content.get("status") in ("pair_done", "done"):
                return content
    return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _seed_archive(archive):
    """Seed skills and tools from their folder READMEs into the vector DB on first run."""
    from archive.skills.loader import seed_skills
    from archive.tools.loader_seed import seed_tools
    seed_skills(archive)
    seed_tools(archive)


def _interrupt_listener(bus, agent_name: str, loop):
    for line in sys.stdin:
        line = line.strip()
        if line.startswith("/btw "):
            asyncio.run_coroutine_threadsafe(bus.interrupt(agent_name, line[5:]), loop)
            print(f"[interrupt → {agent_name}] {line[5:]}")
        elif line == "/status":
            for aid, s in bus.agents_status().items():
                print(f"  {aid}: {s.get('status')} — {s.get('task', s.get('message', ''))[:70]}")


async def main():
    from archive.db import Archive
    from messaging.bus import MessageBus
    from archive.tools.loader import _populate_pointers, _slug
    import shutil

    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-name", default=os.environ.get("AGENT_NAME", ""))
    parser.add_argument("--task", default="")
    parser.add_argument("--max-turns", type=int, default=0)
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    archive = Archive(BASE / "archive")
    bus = MessageBus(BASE / "messaging" / "data")
    _seed_archive(archive)

    if args.agent_name:
        # Running as a named agent (inside Docker or spawned subprocess)
        cfg = AgentConfig.load(args.agent_name, task_override=args.task or None)
        if args.max_turns:
            cfg.max_turns = args.max_turns
        if args.model:
            cfg.model = args.model

        agent = Agent(cfg, archive, bus)

        # Worker: find or create its paired checker, then run together
        # Checkers are always paired with a worker — they don't run standalone
        c_id = cfg.name.replace("-worker", "-checker") if "-worker" in cfg.name else f"{cfg.name}-checker"
        if not (AGENTS_DIR / c_id).exists():
            c_dir = AGENTS_DIR / c_id
            shutil.copytree(AGENTS_DIR / "checker", c_dir, dirs_exist_ok=True)
            c_cfg_data = yaml.safe_load((c_dir / "config" / "agent.yaml").read_text())
            checker_turns = max(cfg.max_turns // 2, 5)
            c_cfg_data.update({"task": f"check: {cfg.task}", "parent": cfg.name, "name": c_id, "max_turns": checker_turns})
            (c_dir / "config" / "agent.yaml").write_text(yaml.dump(c_cfg_data, allow_unicode=True))
            _populate_pointers(c_dir, cfg.task, archive)

        checker_cfg = AgentConfig.load(c_id)
        checker = Agent(checker_cfg, archive, bus)

        loop = asyncio.get_event_loop()
        if sys.stdin.isatty():
            threading.Thread(target=_interrupt_listener, args=(bus, cfg.name, loop), daemon=True).start()

        result = await _run_pair(agent, checker)
        print(f"\ndone={result['done']}")
        if result.get("output"):
            print(result["output"])

    else:
        # Interactive mode: task from CLI
        if not args.task:
            parser.print_help()
            sys.exit(1)

        # Create a fresh worker+checker pair from the canonical configs
        from archive.tools.loader import _slug
        w_id = _slug(args.task, "worker")
        c_id = _slug(args.task, "checker")

        for role, slug in [("worker", w_id), ("checker", c_id)]:
            dest = AGENTS_DIR / slug
            shutil.copytree(AGENTS_DIR / role, dest, dirs_exist_ok=True)
            cfg_data = yaml.safe_load((dest / "config" / "agent.yaml").read_text())
            cfg_data.update({"task": args.task if role == "worker" else f"check: {args.task}",
                             "name": slug, "max_turns": args.max_turns or cfg_data.get("max_turns", 20)})
            if args.model:
                cfg_data["model"] = args.model
            (dest / "config" / "agent.yaml").write_text(yaml.dump(cfg_data, allow_unicode=True))
            _populate_pointers(dest, args.task, archive)

        w_cfg = AgentConfig.load(w_id)
        c_cfg = AgentConfig.load(c_id)
        worker = Agent(w_cfg, archive, bus)
        checker = Agent(c_cfg, archive, bus)

        loop = asyncio.get_event_loop()
        if sys.stdin.isatty():
            threading.Thread(target=_interrupt_listener, args=(bus, w_id, loop), daemon=True).start()
            print(f"[2am] {args.task}")
            print("[2am] /btw <message> to interrupt | /status to see agents\n")

        result = await _run_pair(worker, checker)
        print(f"\ndone={result['done']}")
        if result.get("output"):
            print(result["output"])

        print("\n--- broadcast log ---")
        for e in bus.tail(10):
            c = e["content"]
            if isinstance(c, dict):
                print(f"  [{c.get('agent', e['sender'])}] {c.get('status', '')} {c.get('feedback', c.get('message', ''))[:80]}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _agent_dir(name: str) -> Path:
    """Resolve agents/<name> — all agents live flat under agents/."""
    path = AGENTS_DIR / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_json(raw: str, default: dict) -> dict:
    try:
        return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return default


if __name__ == "__main__":
    asyncio.run(main())
