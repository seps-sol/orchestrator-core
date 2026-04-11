from __future__ import annotations

from datetime import datetime, timezone

MEMORY_LABEL = "seps:memory"
TASK_LABEL = "seps:task"


def tick_title(prefix: str = "seps memory") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{prefix} {ts}"


def format_memory_body(
    *,
    observation: str,
    plan: str,
    action_taken: str,
    dry_run: bool,
    errors: list[str] | None,
) -> str:
    err = "\n".join(f"- {e}" for e in (errors or [])) or "_none_"
    return (
        f"## Tick\n"
        f"- `dry_run`: {dry_run}\n\n"
        f"## Observation\n\n{observation}\n\n"
        f"## Plan\n\n{plan}\n\n"
        f"## Action\n\n{action_taken}\n\n"
        f"## Errors\n\n{err}\n"
    )
