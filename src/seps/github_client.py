from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from seps.config import Settings
from seps.gh_cli import GhError, assert_gh_auth, gh_json, gh_run


def load_child_repo_spec(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / "config" / "child_repos.json"
    return json.loads(path.read_text(encoding="utf-8"))


class OrgClient:
    """Org operations via GitHub CLI (`gh`), not PyGithub."""

    def __init__(self, settings: Settings) -> None:
        assert_gh_auth(settings)
        self._settings = settings
        self._org_login = settings.github_org

    def list_open_issues_with_labels(
        self, repo_name: str, labels: list[str], *, limit: int = 50
    ) -> list[str]:
        repo = f"{self._org_login}/{repo_name}"
        args = [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,title",
        ]
        for lab in labels:
            args.extend(["--label", lab])
        rows = gh_json(args, settings=self._settings)
        if not rows:
            return []
        lines: list[str] = []
        for row in rows:
            lines.append(f"#{row['number']}\t{row['title']}")
        return lines

    def list_public_repo_names(self) -> list[str]:
        rows = gh_json(
            [
                "repo",
                "list",
                self._org_login,
                "--limit",
                "1000",
                "--json",
                "name",
            ],
            settings=self._settings,
        )
        if not rows:
            return []
        return sorted(str(r["name"]) for r in rows)

    def ensure_repo_exists(self, name: str, description: str, *, dry_run: bool) -> str:
        full = f"{self._org_login}/{name}"
        if dry_run:
            return f"[dry-run] would ensure repo {full} via gh repo create"
        view = gh_run(
            ["repo", "view", full, "--json", "name"],
            settings=self._settings,
            check=False,
        )
        if view.returncode == 0:
            return f"repo exists: {full}"
        combined = f"{view.stderr or ''} {view.stdout or ''}".lower()
        if not any(
            s in combined
            for s in ("404", "not found", "could not resolve", "unknown repository")
        ):
            raise GhError(
                cmd=["repo", "view", full],
                stdout=view.stdout,
                stderr=view.stderr,
                returncode=view.returncode,
            )
        gh_run(
            [
                "repo",
                "create",
                full,
                "--public",
                "--description",
                description,
            ],
            settings=self._settings,
            check=True,
        )
        return f"created repo: {full}"
