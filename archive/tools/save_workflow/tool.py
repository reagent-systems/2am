"""
save_workflow — encode a completed automation as a reusable workflow.

Creates archive/workflows/<name>/:
  <name>.py        — Python script (runnable directly, no LLM)
  workflow.yaml    — metadata + step definitions
  description.md   — human-readable description

The Python script is the primary artifact. It calls tool execute() functions
directly and can be run standalone or invoked via run_workflow.
Agents can refine the script over time to optimise or extend the automation.
"""
import json
import re
from pathlib import Path

import yaml
from claude_agent_sdk import tool

_WORKFLOWS_DIR = Path(__file__).parent.parent.parent.parent / "archive" / "workflows"


async def execute(args: dict, archive, bus, parent_id: str) -> str:
    name = args["name"].lower().replace(" ", "-")
    description = args["description"]
    steps_raw = args.get("steps", "[]")

    if isinstance(steps_raw, str):
        try:
            steps = json.loads(steps_raw)
        except json.JSONDecodeError:
            return f"[error: steps must be a JSON array, got: {steps_raw[:100]}]"
    else:
        steps = steps_raw

    wf_dir = _WORKFLOWS_DIR / name
    wf_dir.mkdir(parents=True, exist_ok=True)

    # <name>.py — the primary artifact: a runnable Python script
    (wf_dir / f"{name}.py").write_text(_generate_script(name, description, steps, parent_id))

    # workflow.yaml — metadata and step definitions (source of truth for YAML runner)
    (wf_dir / "workflow.yaml").write_text(yaml.dump({
        "name": name,
        "description": description,
        "version": "1.0",
        "created_by": parent_id,
        "steps": steps,
    }, allow_unicode=True, default_flow_style=False))

    # description.md — human-readable
    step_lines = "\n".join(
        f"  {i+1}. `{s.get('tool', '?')}` — {s.get('id', f'step{i}')}"
        for i, s in enumerate(steps)
    )
    (wf_dir / "description.md").write_text(
        f"# {name}\n\n{description}\n\n## Steps\n\n{step_lines}\n\nCreated by: `{parent_id}`\n"
    )

    id_ = archive.add_workflow(name, description, steps)
    return f"Workflow '{name}' saved (id={id_}). Run via: run_workflow(name='{name}') or python archive/workflows/{name}/{name}.py"


def _generate_script(name: str, description: str, steps: list, created_by: str) -> str:
    """Generate a standalone Python script from workflow steps."""
    slug = name.replace("-", "_")
    prev: dict[str, str] = {}  # step_id → variable name

    step_blocks = []
    for i, step in enumerate(steps):
        step_id = step.get("id", f"step{i}")
        tool_name = step["tool"]
        var = f"{re.sub(r'[^a-z0-9]', '_', step_id)}_result"
        prev[step_id] = var

        args_items = ", ".join(
            f'"{k}": {_to_py(v, prev)}' for k, v in step.get("args", {}).items()
        )
        step_blocks.append(
            f"    # Step: {step_id}\n"
            f"    from archive.tools.{tool_name}.tool import execute as _{slug}_{re.sub(r'[^a-z0-9]', '_', step_id)}\n"
            f"    {var} = await _{slug}_{re.sub(r'[^a-z0-9]', '_', step_id)}({{{args_items}}}, archive, bus, agent_id)"
        )

    last_var = prev.get(
        steps[-1].get("id", f"step{len(steps)-1}") if steps else "",
        '""'
    )

    body = "\n\n".join(step_blocks) if step_blocks else '    pass'

    return f'''\
"""
{name} — {description}

Auto-generated from agent: {created_by}
Agents can edit this script to optimise or extend the automation.

Run standalone:  python archive/workflows/{name}/{name}.py
Run via agent:   run_workflow(name="{name}", inputs={{...}})
"""

DESCRIPTION = "{description}"


async def run(inputs: dict, archive, bus, agent_id: str) -> str:
    """Execute the workflow. Returns the final output string."""
{body}

    return {last_var}


if __name__ == "__main__":
    import asyncio
    from pathlib import Path
    from archive.db import Archive
    from messaging.bus import MessageBus

    BASE = Path(__file__).parent.parent.parent.parent
    archive = Archive(BASE / "archive")
    bus = MessageBus(BASE / "messaging" / "data")
    result = asyncio.run(run({{}}, archive, bus, "cli"))
    print(result)
'''


def _to_py(value, prev: dict[str, str]) -> str:
    """Convert a YAML value (possibly with {{ }} interpolation) to a Python expression."""
    if not isinstance(value, str):
        return repr(value)

    # Whole value is a single interpolation
    m = re.fullmatch(r"\{\{\s*(.+?)\s*\}\}", value)
    if m:
        parts = m.group(1).strip().split(".")
        if parts[0] == "inputs" and len(parts) == 2:
            return f'inputs.get("{parts[1]}", "")'
        if parts[0] == "steps" and len(parts) == 3 and parts[2] == "result":
            return prev.get(parts[1], '""')

    # Mixed string — inline f-string substitution where possible
    def sub(m):
        parts = m.group(1).strip().split(".")
        if parts[0] == "inputs" and len(parts) == 2:
            return f'{{inputs.get("{parts[1]}", "")}}'
        if parts[0] == "steps" and len(parts) == 3:
            return f'{{{prev.get(parts[1], "")}}}'
        return m.group(0)

    if re.search(r"\{\{", value):
        py_str = re.sub(r"\{\{\s*(.+?)\s*\}\}", sub, value)
        return f'f"{py_str}"'

    return repr(value)


def make_tool(archive, bus, parent_id: str):

    @tool(
        "save_workflow",
        "Save a completed, repeatable automation as a workflow so future runs skip the agent loop. "
        "Call this after successfully finishing a task that will need to run again.",
        {"name": str, "description": str, "steps": str},
    )
    async def save_workflow(args):
        text = await execute(args, archive, bus, parent_id)
        return {"content": [{"type": "text", "text": text}]}

    return save_workflow
