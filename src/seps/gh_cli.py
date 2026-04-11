from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from seps.config import Settings


@dataclass
class GhError(Exception):
    cmd: list[str]
    stdout: str
    stderr: str
    returncode: int

    def __str__(self) -> str:
        return (
            f"gh {' '.join(self.cmd)} failed ({self.returncode}): "
            f"{self.stderr.strip() or self.stdout.strip() or 'no output'}"
        )


def gh_installed() -> bool:
    return shutil.which("gh") is not None


def _env_for_gh(settings: Settings | None) -> dict[str, str]:
    env = os.environ.copy()
    token = (settings.github_token.strip() if settings else "") or ""
    if token:
        env["GH_TOKEN"] = token
        env["GITHUB_TOKEN"] = token
    # Non-interactive `gh` (repo create, etc.); avoids deprecated confirmation flags.
    if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI"):
        env.setdefault("GH_PROMPT_DISABLED", "1")
    return env


def gh_run(
    args: list[str],
    *,
    settings: Settings | None = None,
    check: bool = True,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        env=_env_for_gh(settings),
        input=stdin,
    )
    if check and proc.returncode != 0:
        raise GhError(
            cmd=args,
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )
    return proc


def gh_json(args: list[str], *, settings: Settings | None = None) -> Any:
    proc = gh_run(args, settings=settings, check=True)
    if not proc.stdout.strip():
        return None
    return json.loads(proc.stdout)


def git_subprocess_env(settings: Settings | None) -> dict[str, str]:
    """Environment for `git` / `gh` subprocesses (token + non-interactive CI flags)."""
    return _env_for_gh(settings)


def assert_gh_auth(settings: Settings | None) -> None:
    """Fail fast if gh is missing or not logged in (and no PAT in settings)."""
    if not gh_installed():
        raise ValueError(
            "GitHub CLI (gh) is not installed. See https://cli.github.com/"
        )
    token = (settings.github_token.strip() if settings else "") or ""
    if token:
        gh_run(["auth", "status"], settings=settings, check=True)
        return
    gh_run(["auth", "status"], settings=None, check=True)
