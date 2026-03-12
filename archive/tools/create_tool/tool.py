"""
create_tool — write a new MCP tool into archive/tools/.

When a worker needs a capability that doesn't exist, it builds the tool itself.
The tool is discovered automatically on the next agent session.
This is how the system self-extends rather than getting stuck.
"""
from pathlib import Path

from claude_agent_sdk import tool

_TOOLS_DIR = Path(__file__).parent.parent


async def execute(args: dict, archive, bus, parent_id: str) -> str:
    name = args["name"].lower().replace("-", "_").replace(" ", "_")
    description = args["description"]
    code = args["code"]

    tool_dir = _TOOLS_DIR / name
    if tool_dir.exists():
        return f"[error: tool '{name}' already exists — use Bash to edit it directly]"

    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "__init__.py").write_text("")
    (tool_dir / "tool.py").write_text(code)
    (tool_dir / "README.md").write_text(
        f"# {name}\n\n{description}\n\nCreated by: `{parent_id}`\n"
    )

    archive.add_tool(name, description)

    return (
        f"Tool '{name}' created at archive/tools/{name}/tool.py. "
        f"It will be available in the next agent session. "
        f"Spawn a new subagent to use it immediately."
    )


def make_tool(archive, bus, parent_id: str):

    @tool(
        "create_tool",
        "Write a new MCP tool into archive/tools/ when you need a capability that doesn't exist. "
        "The tool is auto-discovered on the next agent session. "
        "Spawn a subagent after creating it to use it immediately.",
        {"name": str, "description": str, "code": str},
    )
    async def create_tool(args):
        text = await execute(args, archive, bus, parent_id)
        return {"content": [{"type": "text", "text": text}]}

    return create_tool
