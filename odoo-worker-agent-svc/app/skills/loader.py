"""Skill file loader — reads and parses YAML+Markdown skill files."""

import logging
from pathlib import Path

import yaml

from app.skills.models import LoadedSkill, SkillMeta

logger = logging.getLogger(__name__)

_DEFAULT_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def load_all_skills(skills_dir: Path | None = None) -> list[LoadedSkill]:
    """Load all .md skill files from the skills directory.

    Parses YAML frontmatter and Markdown body. Logs warnings for
    malformed files but never raises (fail-open).
    """
    directory = skills_dir or _DEFAULT_SKILLS_DIR
    if not directory.is_dir():
        logger.warning("Skills directory not found: %s", directory)
        return []

    skills: list[LoadedSkill] = []
    for path in sorted(directory.glob("*.md")):
        try:
            skill = _parse_skill_file(path)
            if skill:
                skills.append(skill)
                logger.info("Loaded skill: %s (%s)", skill.meta.name, path.name)
        except Exception:
            logger.warning("Failed to parse skill file: %s", path, exc_info=True)

    logger.info("Loaded %d skill(s) from %s", len(skills), directory)
    return skills


def _parse_skill_file(path: Path) -> LoadedSkill | None:
    """Parse a single skill file with YAML frontmatter."""
    content = path.read_text(encoding="utf-8")

    if not content.startswith("---"):
        logger.warning("Skill file %s missing YAML frontmatter", path.name)
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        logger.warning("Skill file %s has malformed frontmatter", path.name)
        return None

    frontmatter = yaml.safe_load(parts[1])
    if not isinstance(frontmatter, dict) or "name" not in frontmatter:
        logger.warning("Skill file %s missing 'name' in frontmatter", path.name)
        return None

    body = parts[2].strip()
    meta = SkillMeta(**frontmatter)

    return LoadedSkill(meta=meta, body=body, file_path=str(path))
