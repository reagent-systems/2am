"""
Archive — single interface for all agent knowledge.

Everything is one vector DB. Types: skill, tool, workflow, knowledge, agent_config.

The agent_config type is special: a fuzzy-matched task description returns
a structured config (tools, system_prompt, role) for spawning the right agent.
That's how the DB bridges task descriptions → agent instantiation.
"""
from pathlib import Path
from . import VectorDB


class Archive:
    def __init__(self, base_path: Path):
        self.db = VectorDB(base_path / "db" / "vectors.json")

    # --- write ---

    def add_skill(self, name: str, content: str, tags: list[str] | None = None) -> str:
        text = f"{name}: {content}"
        return self.db.add(text, {"type": "skill", "name": name, "tags": tags or []})

    def add_tool(self, name: str, description: str, schema: dict | None = None) -> str:
        text = f"{name}: {description}"
        return self.db.add(text, {"type": "tool", "name": name, "schema": schema or {}})

    def add_workflow(self, name: str, description: str, steps: list | None = None) -> str:
        text = f"{name}: {description}"
        return self.db.add(text, {"type": "workflow", "name": name, "steps": steps or []})

    def add_knowledge(self, content: str, source: str = "") -> str:
        return self.db.add(content, {"type": "knowledge", "source": source})

    def add_agent_config(self, name: str, description: str, config: dict) -> str:
        """
        Store an agent config by capability description.
        config = { role, system_prompt, tools, model, max_turns, ... }

        Later: search("analyze a CSV file") → returns this config to spawn the right agent.
        Two similar configs can be blended (vector interpolation) for novel agent types.
        """
        text = f"{name}: {description}"
        return self.db.add(text, {"type": "agent_config", "name": name, "config": config})

    # --- read ---

    def search(self, query: str, k: int = 5, type_: str | None = None) -> list[dict]:
        return self.db.search(query, k, type_filter=type_)

    def get(self, id_: str) -> dict | None:
        return self.db.get(id_)

    def get_agent_config(self, task: str) -> dict | None:
        """
        Fuzzy-match a task description to the best agent config in the archive.
        Returns the config dict if score is above threshold, else None.
        """
        results = self.db.search(task, k=1, type_filter="agent_config")
        if results and results[0]["score"] > 0.15:
            return results[0]["metadata"]["config"]
        return None

    def blend_configs(self, task: str, k: int = 2) -> dict | None:
        """
        Return k best-matching agent configs blended together.
        Used for novel tasks that cross multiple capabilities.
        """
        results = self.db.search(task, k=k, type_filter="agent_config")
        if not results:
            return None
        # Simple blend: union tools, concatenate system prompts
        tools = set()
        prompts = []
        for r in results:
            cfg = r["metadata"]["config"]
            tools.update(cfg.get("tools", []))
            if p := cfg.get("system_prompt"):
                prompts.append(p)
        base = results[0]["metadata"]["config"].copy()
        base["tools"] = list(tools)
        base["system_prompt"] = " ".join(prompts)
        return base

    def format_context(self, results: list[dict]) -> str:
        """Format search results as a context string for agent prompts."""
        if not results:
            return ""
        lines = []
        for r in results:
            m = r["metadata"]
            label = f"[{m.get('type', '?')}:{m.get('name', r['id'])}]"
            lines.append(f"{label} {r['text'][:300]}")
        return "\n".join(lines)
