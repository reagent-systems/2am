"""
run_workflow — execute a saved workflow without an agent loop.

This is the runtime counterpart to save_workflow. Agents call this when
they discover a matching workflow in the archive instead of redoing the work.
"""
import json

from claude_agent_sdk import tool


async def execute(args: dict, archive, bus, parent_id: str) -> str:
    """Direct callable for the workflow executor (workflows can call other workflows)."""
    from archive.workflows.executor import run

    name = args["name"]
    inputs_raw = args.get("inputs", "{}")
    if isinstance(inputs_raw, str):
        try:
            inputs = json.loads(inputs_raw) if inputs_raw else {}
        except json.JSONDecodeError:
            inputs = {}
    else:
        inputs = inputs_raw or {}

    result = await run(name, inputs, archive, bus, parent_id)
    return result["result"]


def make_tool(archive, bus, parent_id: str):

    @tool(
        "run_workflow",
        "Execute a saved workflow by name. Runs the automation directly without spawning an agent. "
        "Use archive_search(type='workflow') to discover available workflows first.",
        {"name": str, "inputs": str},
    )
    async def run_workflow(args):
        text = await execute(args, archive, bus, parent_id)
        return {"content": [{"type": "text", "text": text}]}

    return run_workflow
