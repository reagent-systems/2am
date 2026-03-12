"""
Discovers and loads all tools from archive/tools/*/tool.py.

Each tool folder that contains a tool.py must export:
    make_tool(archive, bus, parent_id) -> MCP tool

Also owns the agent-naming and pointer helpers used by main.py and tool scripts.
"""
import importlib
import re
import yaml
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server

BASE = Path(__file__).parent.parent.parent
AGENTS_DIR = BASE / "agents"
_TOOLS_DIR = Path(__file__).parent

_STOP = {
    "a", "an", "the", "to", "for", "and", "or", "of", "in", "on", "at",
    "is", "it", "by", "with", "that", "this", "from", "be", "do",
}


def create_agent_tools(archive, bus, parent_id: str):
    """
    Build the MCP server for an agent session.
    Discovers every tool.py under archive/tools/ and calls make_tool() on each.
    """
    tools = []
    for tool_dir in sorted(_TOOLS_DIR.iterdir()):
        if tool_dir.is_dir() and (tool_dir / "tool.py").exists():
            mod = importlib.import_module(f"archive.tools.{tool_dir.name}.tool")
            tools.append(mod.make_tool(archive, bus, parent_id))

    return create_sdk_mcp_server(f"2am-tools-{parent_id}", tools=tools)


def _slug(task: str, role: str) -> str:
    """Descriptive agent slug from task words + role suffix. Handles collisions."""
    words = re.sub(r"[^a-z0-9 ]", " ", task.lower()).split()
    words = [w for w in words if w not in _STOP and len(w) > 1][:5]
    slug = "-".join(words) if words else role
    name = f"{slug}-{role}"
    candidate, i = name, 2
    while (AGENTS_DIR / candidate).exists():
        candidate, i = f"{name}-{i}", i + 1
    return candidate


def _populate_pointers(agent_dir: Path, task: str, archive):
    """Search archive for the task and write real IDs to pointers.yaml."""
    skills = archive.search(task, k=3, type_="skill")
    tools = archive.search(task, k=3, type_="tool")
    knowledge = archive.search(task, k=2, type_="knowledge")
    workflows = archive.search(task, k=3, type_="workflow")

    pointers = {
        "skills":    [{"id": r["id"], "name": r["metadata"].get("name"), "score": r["score"]} for r in skills    if r["score"] > 0.05],
        "tools":     [{"id": r["id"], "name": r["metadata"].get("name"), "score": r["score"]} for r in tools     if r["score"] > 0.05],
        "knowledge": [{"id": r["id"], "score": r["score"], "preview": r["text"][:80]}          for r in knowledge if r["score"] > 0.05],
        "workflows": [{"id": r["id"], "name": r["metadata"].get("name"), "score": r["score"]} for r in workflows if r["score"] > 0.1],
    }
    (agent_dir / "config" / "pointers.yaml").write_text(yaml.dump(pointers, allow_unicode=True))

    skill_names = [r["metadata"].get("name", "") for r in skills if r["score"] > 0.1]
    if skill_names:
        cfg_path = agent_dir / "config" / "agent.yaml"
        cfg = yaml.safe_load(cfg_path.read_text())
        cfg["system_prompt"] = cfg.get("system_prompt", "") + f"\n\nApplicable skills: {', '.join(skill_names)}"
        cfg_path.write_text(yaml.dump(cfg, allow_unicode=True))
