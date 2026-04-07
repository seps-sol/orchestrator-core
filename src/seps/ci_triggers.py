from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_ci_triggers(repo_root: Path) -> dict[str, list[str]]:
    path = repo_root / "config" / "ci_triggers.json"
    if not path.is_file():
        return {}
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in raw.items():
        if isinstance(v, list):
            out[str(k)] = [str(x) for x in v]
    return out
