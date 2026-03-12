"""
Workflow executor — runs saved automations without an agent loop.

Each workflow lives in archive/workflows/<name>/:
  <name>.py        — Python script with async run(inputs, archive, bus, agent_id)
  workflow.yaml    — metadata + step definitions (source of truth / fallback)
  description.md   — human-readable description

Execution priority:
  1. If <name>.py exists → import and call run() directly (pure Python, no LLM)
  2. Otherwise → execute workflow.yaml steps via tool.execute() functions

This lets workflows graduate from YAML step chains into hand-optimised Python
scripts as they mature — no agent involvement needed once a script exists.
"""
import importlib
import importlib.util
import re
import sys
import yaml
from pathlib import Path

_WORKFLOWS_DIR = Path(__file__).parent
_TOOLS_DIR = _WORKFLOWS_DIR.parent / "tools"


def load(name: str) -> dict:
    """Load workflow metadata from workflow.yaml."""
    path = _WORKFLOWS_DIR / name / "workflow.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Workflow '{name}' not found at {path}")
    return yaml.safe_load(path.read_text())


def list_workflows() -> list[str]:
    """Return names of all saved workflows (have a workflow.yaml)."""
    return [
        d.name for d in sorted(_WORKFLOWS_DIR.iterdir())
        if d.is_dir() and (d / "workflow.yaml").exists()
    ]


async def run(name: str, inputs: dict, archive, bus, agent_id: str) -> dict:
    """
    Execute a workflow by name.

    Prefers the Python script (<name>.py) if it exists.
    Falls back to running workflow.yaml steps via tool.execute() functions.

    Returns {"success": bool, "result": str, "workflow": str, "via": "script"|"yaml"}
    """
    wf_dir = _WORKFLOWS_DIR / name
    script = wf_dir / f"{name}.py"

    if script.exists():
        # Load and call the Python script directly — no LLM, pure automation
        mod = _import_script(name, script)
        result = await mod.run(inputs, archive, bus, agent_id)
        return {"success": True, "result": result, "workflow": name, "via": "script"}

    # Fall back to YAML step execution
    wf = load(name)
    result, steps_log = await _run_steps(wf.get("steps", []), inputs, archive, bus, agent_id)
    return {"success": True, "result": result, "steps": steps_log, "workflow": name, "via": "yaml"}


def _import_script(name: str, path: Path):
    """Import a workflow Python script by file path (avoids package naming issues)."""
    module_name = f"_workflow_{name.replace('-', '_')}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


async def _run_steps(steps: list, inputs: dict, archive, bus, agent_id: str) -> tuple[str, list]:
    """Execute YAML step chain with variable interpolation."""
    ctx = {"inputs": inputs, "steps": {}}
    steps_log = []

    for step in steps:
        step_id = step.get("id", f"step{len(steps_log)}")
        tool_name = step["tool"]
        args = {k: _resolve(v, ctx) for k, v in step.get("args", {}).items()}

        result = await _call_tool(tool_name, args, archive, bus, agent_id)
        ctx["steps"][step_id] = {"result": result}
        steps_log.append({"id": step_id, "tool": tool_name, "result": result})

    final = steps_log[-1]["result"] if steps_log else ""
    return final, steps_log


def _resolve(value, ctx: dict):
    """Interpolate {{ variable.path }} references."""
    if not isinstance(value, str):
        return value

    def sub(m):
        parts = m.group(1).strip().split(".")
        v = ctx
        for p in parts:
            v = v.get(p, "") if isinstance(v, dict) else ""
        return str(v)

    return re.sub(r"\{\{\s*(.+?)\s*\}\}", sub, value)


async def _call_tool(tool_name: str, args: dict, archive, bus, agent_id: str) -> str:
    """Call a tool's execute() function directly."""
    tool_py = _TOOLS_DIR / tool_name / "tool.py"
    if not tool_py.exists():
        return f"[error: tool '{tool_name}' not found]"
    mod = importlib.import_module(f"archive.tools.{tool_name}.tool")
    if not hasattr(mod, "execute"):
        return f"[error: tool '{tool_name}' has no execute()]"
    return await mod.execute(args, archive, bus, agent_id)
