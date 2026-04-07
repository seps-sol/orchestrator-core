from __future__ import annotations

import argparse
import sys

from seps.config import get_settings
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

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    cli()
