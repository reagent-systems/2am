"""Seed existing workflow definitions into the archive vector DB on first run."""
import yaml
from pathlib import Path

_WORKFLOWS_DIR = Path(__file__).parent


def seed_workflows(archive):
    if archive.db.all(type_filter="workflow"):
        return  # already seeded
    for wf_dir in sorted(_WORKFLOWS_DIR.iterdir()):
        wf_yaml = wf_dir / "workflow.yaml"
        if not (wf_dir.is_dir() and wf_yaml.exists()):
            continue
        wf = yaml.safe_load(wf_yaml.read_text())
        archive.add_workflow(
            name=wf_dir.name,
            description=wf.get("description", wf_dir.name),
            steps=wf.get("steps", []),
        )
