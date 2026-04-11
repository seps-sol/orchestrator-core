from __future__ import annotations

from pathlib import Path

_MAX_STEERING_CHARS = 12_000


def load_steering_context(repo_root: Path) -> str:
    """Product steering text injected into planner context (optional file)."""
    path = repo_root / "config" / "steering.md"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) > _MAX_STEERING_CHARS:
        text = text[:_MAX_STEERING_CHARS] + "\n\n_(truncated for context limit)_\n"
    return text
