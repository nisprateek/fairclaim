"""Loads versioned Agent Skill documents — one directory per skill, anchored
by a SKILL.md (YAML frontmatter + markdown body) — so agent instructions are
built from lawyer-reviewable documents, not hard-coded prompt strings.
"""

from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent


def split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter, body) of a SKILL.md; ("", text) if no leading block."""
    if text.startswith("---\n"):
        closing = text.find("\n---\n", 4)
        if closing != -1:
            return text[4:closing], text[closing + 5 :]
    return "", text


def load_skill(name: str) -> str:
    """Instruction body of backend/skills/<name>/SKILL.md.

    The frontmatter (name/description/version) is the Agent Skills routing
    layer; every skill here is statically bound to one agent, so only the
    body belongs in the model's instruction.
    """
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    return split_frontmatter(text)[1]
