"""
Seeds all skills from archive/skills/*/README.md into the archive on first run.
Each skill folder's README.md is the canonical source — name comes from the folder.
"""
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent


def seed_skills(archive):
    """Load skills into the archive if not already present."""
    if archive.db.all(type_filter="skill"):
        return  # already seeded

    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        if skill_dir.is_dir() and (skill_dir / "README.md").exists():
            content = (skill_dir / "README.md").read_text()
            archive.add_skill(name=skill_dir.name, content=content)
