# create_tool

Write a new MCP tool into `archive/tools/` when you need a capability that doesn't exist.

Use this when:
- You need to call an API that has no existing tool
- You need to process a file format nothing handles yet
- A subtask keeps failing because the right tool is missing

The new tool is automatically discovered by `loader.py` on the next agent session.
Other agents and workflows can use it immediately after creation.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| `name` | string | Snake-case tool name (e.g. `fetch_rss`, `parse_pdf`) |
| `description` | string | What the tool does — used for archive search |
| `code` | string | Complete Python source for `tool.py` |

## Tool code requirements

The code must define:
- `async def execute(args, archive, bus, parent_id) -> str` — called by workflows
- `def make_tool(archive, bus, parent_id)` — returns the MCP tool for agent sessions

Minimal template:
```python
from claude_agent_sdk import tool

async def execute(args: dict, archive, bus, parent_id: str) -> str:
    # implementation
    return "result"

def make_tool(archive, bus, parent_id: str):
    @tool("tool_name", "description", {"arg": str})
    async def _tool(args):
        return {"content": [{"type": "text", "text": await execute(args, archive, bus, parent_id)}]}
    return _tool
```
