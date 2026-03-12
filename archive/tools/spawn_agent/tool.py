import json
import shutil
from pathlib import Path

import yaml
from claude_agent_sdk import tool

BASE = Path(__file__).parent.parent.parent.parent
AGENTS_DIR = BASE / "agents"


def make_tool(archive, bus, parent_id: str):
    from archive.tools.loader import _slug, _populate_pointers

    @tool(
        "spawn_agent",
        "Spawn a new agent to handle a subtask or blocker. "
        "Returns agent_id — use it with the 'wait' plan action to block until done.",
        {"task": str, "role": str},
    )
    async def spawn_agent(args):
        task = args["task"]
        role = args.get("role", "worker")
        agent_id = _slug(task, role)
        agent_dir = AGENTS_DIR / agent_id

        base_dir = AGENTS_DIR / role
        if not base_dir.exists():
            base_dir = AGENTS_DIR / "worker"
        shutil.copytree(base_dir, agent_dir, dirs_exist_ok=True)

        cfg_path = agent_dir / "config" / "agent.yaml"
        cfg = yaml.safe_load(cfg_path.read_text())
        cfg["task"] = task
        cfg["parent"] = parent_id
        cfg["name"] = agent_id
        cfg_path.write_text(yaml.dump(cfg, allow_unicode=True))

        _populate_pointers(agent_dir, task, archive)
        _start_container(agent_id, agent_dir)

        return {"content": [{"type": "text", "text": json.dumps({"agent_id": agent_id, "status": "started", "task": task})}]}

    return spawn_agent


def _start_container(agent_id: str, agent_dir: Path):
    import os
    import subprocess

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    archive_dir = str(BASE / "archive")
    messaging_dir = str(BASE / "messaging" / "data")
    workspace_dir = str(agent_dir / "workspace")

    docker_cmd = [
        "docker", "run", "-d",
        "--name", agent_id,
        "-e", f"AGENT_NAME={agent_id}",
        "-e", f"ANTHROPIC_API_KEY={api_key}",
        "-v", f"{archive_dir}:/2am/archive",
        "-v", f"{messaging_dir}:/2am/messaging/data",
        "-v", f"{workspace_dir}:/2am/agents/{agent_id}/workspace",
        "2am-agent",
        "python", "-m", "main.main", "--agent-name", agent_id,
    ]

    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=3)
        subprocess.Popen(docker_cmd)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        subprocess.Popen(
            ["python", "-m", "main.main", "--agent-name", agent_id],
            cwd=str(BASE),
            env={**os.environ, "AGENT_NAME": agent_id},
        )
