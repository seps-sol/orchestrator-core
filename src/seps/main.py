from __future__ import annotations

import argparse
import sys

from seps.bootstrap import bootstrap_child_workflows
from seps.config import get_settings
from seps.execute_task import run_execute_issue
from seps.gh_cli import GhError
from seps.github_client import OrgClient
from seps.graph import build_graph


def cli() -> None:
    parser = argparse.ArgumentParser(description="SEPS orchestrator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    once = sub.add_parser("once", help="Run one observe→plan→act cycle")
    once.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan with LLM but skip repo creation",
    )

    tasks = sub.add_parser("tasks", help="Agent task board (GitHub Issues)")
    tasks_sub = tasks.add_subparsers(dest="tasks_cmd", required=True)
    tasks_sub.add_parser("list", help="List open issues labeled seps:task")

    memory = sub.add_parser("memory", help="Durable orchestrator memory (GitHub Issues)")
    memory_sub = memory.add_subparsers(dest="memory_cmd", required=True)
    memory_sub.add_parser("list", help="List recent issues labeled seps:memory")

    boot = sub.add_parser("bootstrap", help="Provision org resources from orchestrator-core")
    boot_sub = boot.add_subparsers(dest="boot_cmd", required=True)
    wf = boot_sub.add_parser(
        "workflows",
        help="Push manual-only self-run workflow to every repo in config/child_repos.json",
    )
    wf.add_argument(
        "--dry-run",
        action="store_true",
        help="Print targets only (no GitHub writes)",
    )

    ex = sub.add_parser(
        "execute",
        help="Open a draft PR with a handoff doc for a seps:task issue (clone, branch, push)",
    )
    ex.add_argument(
        "--repo",
        required=True,
        help="Short repo name under GITHUB_ORG (e.g. agent-marketplace)",
    )
    ex.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    ex.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without cloning or opening a PR",
    )
    ex.add_argument(
        "--with-llm",
        action="store_true",
        help="Append an LLM-written implementation outline to the handoff doc",
    )

    args = parser.parse_args()
    settings = get_settings()

    if args.cmd == "once":
        graph = build_graph(settings)
        initial = {
            "observation": "",
            "plan": "",
            "action_taken": "",
            "dry_run": args.dry_run,
        }
        out = graph.invoke(initial)
        print("--- observation ---\n", out["observation"], sep="")
        print("--- plan ---\n", out["plan"], sep="")
        print("--- action ---\n", out["action_taken"], sep="")
        if out.get("memory_note"):
            print("--- memory ---\n", out["memory_note"], sep="")
        if out.get("errors"):
            print("--- errors ---\n", out["errors"], sep="")
        return

    if args.cmd == "tasks" and args.tasks_cmd == "list":
        try:
            client = OrgClient(settings)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        lines = client.list_open_issues_with_labels(
            settings.github_tasks_repo, ["seps:task"]
        )
        if not lines:
            print(f"No open seps:task issues in {settings.github_tasks_repo}.")
            return
        for line in lines:
            print(line)
        return

    if args.cmd == "memory" and args.memory_cmd == "list":
        try:
            client = OrgClient(settings)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        rows = client.list_recent_memories(
            settings.github_memory_repo, limit=30, brief=False
        )
        if not rows:
            print(f"No seps:memory issues in {settings.github_memory_repo}.")
            return
        for line in rows:
            print(line)
        return

    if args.cmd == "bootstrap" and args.boot_cmd == "workflows":
        try:
            lines = bootstrap_child_workflows(settings, dry_run=args.dry_run)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        for line in lines:
            print(line)
        return

    if args.cmd == "execute":
        try:
            msg = run_execute_issue(
                settings,
                args.repo,
                args.issue,
                dry_run=args.dry_run,
                with_llm=args.with_llm,
            )
        except (ValueError, GhError) as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        print(msg)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    cli()
