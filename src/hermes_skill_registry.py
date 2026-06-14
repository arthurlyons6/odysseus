"""Hermes skill registry — scan ``C:/Users/13464/.hermes/skills`` and ingest skills into Odysseus."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HERMES_SKILLS_DIR = "C:/Users/13464/.hermes/skills"


def scan_hermes_skills(root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return Hermes skills as raw metadata dicts (name, description, category, raw body)."""
    root = root or HERMES_SKILLS_DIR
    base = Path(root)
    if not base.is_dir():
        return []

    results = []
    for entry in base.iterdir():
        skill_md = entry / "SKILL.md"
        if entry.is_dir() and skill_md.is_file():
            try:
                text = skill_md.read_text(encoding="utf-8")
                desc = ""
                name = entry.name
                if "\n" in text:
                    first_line, rest = text.split("\n", 1)
                    if first_line.startswith("name:"):
                        name = first_line.split(":", 1)[1].strip()
                if text.count("---") >= 2:
                    _, yaml_block, after = text.split("---", 2)
                    for yaml_line in yaml_block.splitlines():
                        if ":" in yaml_line:
                            key, value = yaml_line.split(":", 1)
                            if key.strip().lower() == "description":
                                desc = value.strip().strip('"\'')
                                break
                if not desc:
                    desc = name.replace("-", " ").replace("_", " ").title()
                results.append(
                    {
                        "path": str(skill_md),
                        "name": name,
                        "description": desc,
                        "category": "hermes",
                        "raw": text,
                        "raw_snippet": text[:1200],
                    }
                )
            except Exception as exc:
                logger.debug(
                    "Failed to read Hermes skill %s: %s", entry.name, exc
                )
    return results


class HermesSkillRegistry:
    """Lightweight helper around a ``SkillsManager`` for onboarding Hermes skills."""

    EXACT_PATH = HERMES_SKILLS_DIR

    @classmethod
    def scan(cls) -> List[Dict[str, Any]]:
        return scan_hermes_skills(cls.EXACT_PATH)

    @classmethod
    def ingest(cls, skills_manager) -> Dict[str, Any]:
        """Import Hermes skills into the given ``skills_manager`` such that they
        become available via ``skills_manager.load_all()``.
        """
        skills = cls.scan()
        existing_subset = set(
            s.get("name") for s in skills_manager.load_all() if isinstance(s, dict)
        )
        added = []
        for item in skills:
            name = item.get("name") or ""
            if name in existing_subset:
                continue
            try:
                skills_manager.add_skill(
                    name=item.get("name"),
                    description=item.get("description", ""),
                    category=item.get("category", "hermes"),
                    when_to_use="Hermes skill ingested from C:/Users/13464/.hermes/skills\n\n"
                    + (item.get("raw") or "").strip(),
                    procedure=[],
                    pitfalls=[],
                    verification=[],
                    owner=None,
                    source="hermes",
                )
                added.append(name)
            except Exception as exc:
                logger.warning("Hermes skill ingest failed for %s: %s", name, exc)

        return {"available": skills, "added": added}
