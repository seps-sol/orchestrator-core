from __future__ import annotations

# Keys the planner must echo as single-line "KEY: value" directives (see graph prompts).
DIRECTIVE_KEYS = frozenset(
    {
        "NEXT_REPO",
        "SEPS_OPEN_TASK",
        "SEPS_TASK_TITLE",
        "SEPS_TASK_DETAIL",
        "SEPS_TASK_REPO",
    }
)


def parse_plan_directives(plan: str) -> dict[str, str]:
    """Parse trailing machine lines from the LLM plan. Last occurrence wins per key."""
    found: dict[str, str] = {}
    for raw in plan.splitlines():
        line = raw.strip()
        if ":" not in line:
            continue
        key_part, _, value = line.partition(":")
        kn = key_part.strip().upper().replace(" ", "_")
        if kn in DIRECTIVE_KEYS:
            found[kn] = value.strip()
    return found
