"""
Seeds tool descriptions from archive/tools/*/README.md into the archive on first run.
"""
from pathlib import Path

_TOOLS_DIR = Path(__file__).parent


def seed_tools(archive):
    """Load tool descriptions into the archive if not already present."""
    if archive.db.all(type_filter="tool"):
        return  # already seeded

    for tool_dir in sorted(_TOOLS_DIR.iterdir()):
        if tool_dir.is_dir() and (tool_dir / "README.md").exists():
            content = (tool_dir / "README.md").read_text()
            # First line after # is the name
            name = tool_dir.name
            archive.add_tool(name=name, description=content)
