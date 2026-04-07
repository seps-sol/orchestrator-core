from __future__ import annotations

from pathlib import Path

from seps.config import Settings
from seps.gh_cli import GhError
from seps.github_client import OrgClient, load_child_repo_spec

CHILD_WORKFLOW_PATH = ".github/workflows/seps-self-run.yml"


def _template_text() -> str:
    path = Path(__file__).resolve().parent / "child_self_run.workflow.yml"
    return path.read_text(encoding="utf-8")


def bootstrap_child_workflows(settings: Settings, *, dry_run: bool = False) -> list[str]:
    """Ensure every repo in child_repos.json has the 5-minute self-run workflow."""
    client = OrgClient(settings)
    specs = load_child_repo_spec(settings.repo_root)
    content = _template_text()
    out: list[str] = []
    for spec in specs:
        name = str(spec["name"])
        if not client.repo_exists(name):
            out.append(f"{name}: skip (repo not found)")
            continue
        try:
            msg = client.put_repo_file_if_changed(
                name,
                CHILD_WORKFLOW_PATH,
                content,
                message="SEPS: sync 5m self-run workflow",
                dry_run=dry_run,
            )
            out.append(f"{name}: {msg}")
        except GhError as exc:
            out.append(f"{name}: gh error ({exc})")
    return out
