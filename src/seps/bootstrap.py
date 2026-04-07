from __future__ import annotations

import json
from pathlib import Path

from seps.ci_triggers import load_ci_triggers
from seps.config import Settings
from seps.gh_cli import GhError
from seps.github_client import OrgClient, load_child_repo_spec

CHILD_WORKFLOW_PATH = ".github/workflows/seps-self-run.yml"
_PLACEHOLDER = "__SEPS_DOWNSTREAM_JSON__"
_REUSABLE_PLACEHOLDER = "__SEPS_REUSABLE_ORCHESTRATE__"


def _template_text() -> str:
    path = Path(__file__).resolve().parent / "child_self_run.workflow.yml"
    return path.read_text(encoding="utf-8")


def render_child_workflow(
    triggers: dict[str, list[str]], repo_name: str, github_org: str
) -> str:
    tpl = _template_text()
    if _PLACEHOLDER not in tpl or _REUSABLE_PLACEHOLDER not in tpl:
        raise RuntimeError("child workflow template missing bootstrap placeholder(s)")
    downstream = triggers.get(repo_name, [])
    blob = json.dumps(downstream, separators=(",", ":"))
    uses_ref = (
        f"{github_org}/orchestrator-core/.github/workflows/seps-child-orchestrate.yml@main"
    )
    return tpl.replace(_PLACEHOLDER, blob).replace(_REUSABLE_PLACEHOLDER, uses_ref)


def bootstrap_child_workflows(settings: Settings, *, dry_run: bool = False) -> list[str]:
    """Ensure every repo in child_repos.json has the 5-minute self-run workflow."""
    client = OrgClient(settings)
    specs = load_child_repo_spec(settings.repo_root)
    triggers = load_ci_triggers(settings.repo_root)
    out: list[str] = []
    for spec in specs:
        name = str(spec["name"])
        if not client.repo_exists(name):
            out.append(f"{name}: skip (repo not found)")
            continue
        try:
            content = render_child_workflow(triggers, name, settings.github_org)
            msg = client.put_repo_file_if_changed(
                name,
                CHILD_WORKFLOW_PATH,
                content,
                message="SEPS: sync self-run workflow + cross-repo triggers",
                dry_run=dry_run,
            )
            out.append(f"{name}: {msg}")
        except GhError as exc:
            out.append(f"{name}: gh error ({exc})")
    return out
