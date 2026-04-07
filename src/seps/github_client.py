from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from github import Auth, Github, GithubException

from seps.config import Settings


def load_child_repo_spec(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / "config" / "child_repos.json"
    return json.loads(path.read_text(encoding="utf-8"))


class OrgClient:
    def __init__(self, settings: Settings) -> None:
        token = settings.github_token.strip()
        if not token:
            raise ValueError("GITHUB_TOKEN is required for GitHub actions")
        self._g = Github(auth=Auth.Token(token))
        self._org = self._g.get_organization(settings.github_org)
        self._org_login = settings.github_org

    def list_public_repo_names(self) -> list[str]:
        names: list[str] = []
        for repo in self._org.get_repos():
            names.append(repo.name)
        return sorted(names)

    def ensure_repo_exists(self, name: str, description: str, *, dry_run: bool) -> str:
        if dry_run:
            return f"[dry-run] would create repo {self._org_login}/{name}"
        try:
            self._org.get_repo(name)
            return f"repo exists: {self._org_login}/{name}"
        except GithubException as e:
            if e.status != 404:
                raise
        self._org.create_repo(
            name=name,
            description=description,
            private=False,
            auto_init=True,
        )
        return f"created repo: {self._org_login}/{name}"
