from __future__ import annotations

import argparse
import sys

from seps.config import get_settings
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
    args = parser.parse_args()

    if args.cmd != "once":
        parser.print_help()
        sys.exit(1)

    settings = get_settings()
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


if __name__ == "__main__":
    cli()
