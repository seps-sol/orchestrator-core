from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path
from typing import Any

from seps.config import Settings
from seps.gh_cli import GhError, assert_gh_auth, gh_json, gh_run
from seps.issue_memory import MEMORY_LABEL


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

    def ensure_memory_label(self, repo_name: str) -> None:
        repo = f"{self._org_login}/{repo_name}"
        gh_run(
            [
                "label",
                "create",
                MEMORY_LABEL,
                "--repo",
                repo,
                "--color",
                "C5DEF5",
                "--description",
                "SEPS orchestrator durable memory (append-only tick log)",
            ],
            settings=self._settings,
            check=False,
        )

    def list_recent_memories(
        self,
        repo_name: str,
        *,
        limit: int = 12,
        brief: bool = False,
        body_preview: int = 320,
    ) -> list[str]:
        """Closed + open issues labeled seps:memory, newest first."""
        repo = f"{self._org_login}/{repo_name}"
        fields = "number,title,updatedAt" if brief else "number,title,body,updatedAt"
        rows = gh_json(
            [
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                "all",
                "--limit",
                str(limit),
                "--json",
                fields,
                "--label",
                MEMORY_LABEL,
            ],
            settings=self._settings,
        )
        if not rows:
            return []
        lines: list[str] = []
        for row in rows:
            if brief:
                lines.append(
                    f"#{row['number']}\t{row['title']}\t({row.get('updatedAt', '')})"
                )
                continue
            body = str(row.get("body") or "")
            excerpt = body.replace("\n", " ").strip()
            if len(excerpt) > body_preview:
                excerpt = excerpt[: body_preview - 1] + "…"
            lines.append(
                f"#{row['number']}\t{row['title']}\t({row.get('updatedAt', '')})\t{excerpt}"
            )
        return lines

    def create_memory_issue(
        self, repo_name: str, title: str, body: str, *, dry_run: bool
    ) -> str:
        repo = f"{self._org_login}/{repo_name}"
        if dry_run:
            return f"[dry-run] would create {MEMORY_LABEL} issue on {repo}"
        self.ensure_memory_label(repo_name)
        path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".md",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(body)
                path = tmp.name
            proc = gh_run(
                [
                    "issue",
                    "create",
                    "--repo",
                    repo,
                    "--title",
                    title,
                    "--label",
                    MEMORY_LABEL,
                    "--body-file",
                    path,
                ],
                settings=self._settings,
                check=True,
            )
        finally:
            if path:
                Path(path).unlink(missing_ok=True)
        url = (proc.stdout or "").strip()
        return url or f"created memory issue on {repo}"

    def repo_exists(self, name: str) -> bool:
        full = f"{self._org_login}/{name}"
        proc = gh_run(
            ["repo", "view", full, "--json", "name"],
            settings=self._settings,
            check=False,
        )
        return proc.returncode == 0

    def default_branch(self, repo_name: str) -> str:
        full = f"{self._org_login}/{repo_name}"
        row = gh_json(
            ["repo", "view", full, "--json", "defaultBranchRef"],
            settings=self._settings,
        )
        ref = row.get("defaultBranchRef") if row else None
        if ref and ref.get("name"):
            return str(ref["name"])
        return "main"

    def put_repo_file_if_changed(
        self,
        repo_name: str,
        path: str,
        content: str,
        message: str,
        *,
        dry_run: bool,
    ) -> str:
        """Create or update a single file via Contents API; skip if bytes match."""
        api_path = f"repos/{self._org_login}/{repo_name}/contents/{path}"
        if dry_run:
            return f"[dry-run] would PUT {path}"
        branch = self.default_branch(repo_name)
        proc = gh_run(
            ["api", f"{api_path}?ref={branch}"],
            settings=self._settings,
            check=False,
        )
        want = content.encode("utf-8")
        b64_new = base64.b64encode(want).decode("ascii")

        data: dict[str, Any] | None = None
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                data = None

        if data and data.get("type") == "file":
            existing_b64 = str(data.get("content") or "").replace("\n", "")
            if existing_b64:
                try:
                    got = base64.b64decode(existing_b64)
                    if got == want:
                        return "unchanged"
                except (ValueError, OSError):
                    pass
            sha = data.get("sha")
            if not sha:
                return "unexpected API response (missing sha)"
            payload: dict[str, str] = {
                "message": message,
                "content": b64_new,
                "sha": sha,
                "branch": branch,
            }
            verb = "updated"
        else:
            payload = {
                "message": message,
                "content": b64_new,
                "branch": branch,
            }
            verb = "created"

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            json.dump(payload, tmp)
            tmp_path = tmp.name
        try:
            gh_run(
                ["api", "-X", "PUT", api_path, "--input", tmp_path],
                settings=self._settings,
                check=True,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return verb

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
