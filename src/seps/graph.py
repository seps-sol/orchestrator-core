from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from seps.config import Settings
from seps.gh_cli import GhError
from seps.github_client import OrgClient, load_child_repo_spec
from seps.issue_memory import format_memory_body, tick_title
from seps.llm import get_chat_model
from seps.state import OrchestratorState


def build_graph(settings: Settings) -> StateGraph:
    specs = load_child_repo_spec(settings.repo_root)
    org_client: OrgClient | None
    try:
        org_client = OrgClient(settings)
    except ValueError:
        org_client = None
    llm = get_chat_model(settings)

    def observe(state: OrchestratorState) -> dict[str, Any]:
        lines: list[str] = []
        if org_client:
            try:
                repos = org_client.list_public_repo_names()
                lines.append(f"Org repos ({len(repos)}): {', '.join(repos) or '(none)'}")
                try:
                    task_lines = org_client.list_open_issues_with_labels(
                        settings.github_tasks_repo, ["seps:task"]
                    )
                    if task_lines:
                        lines.append(
                            f"Open agent tasks in {settings.github_tasks_repo} (label seps:task):"
                        )
                        for t in task_lines:
                            lines.append(f"  {t}")
                    else:
                        lines.append(
                            f"No open `seps:task` issues in {settings.github_tasks_repo}."
                        )
                except GhError as exc:
                    if "could not resolve" in str(exc).lower():
                        lines.append(
                            f"Task board: no repo `{settings.github_org}/{settings.github_tasks_repo}` yet "
                            "(create it or set SEPS_TASKS_REPO)."
                        )
                    else:
                        lines.append(f"Task board: could not list issues ({exc}).")

                try:
                    mem = org_client.list_recent_memories(
                        settings.github_memory_repo, limit=8, brief=True
                    )
                    if mem:
                        lines.append(
                            f"Durable memory ({settings.github_memory_repo}, label seps:memory), recent:"
                        )
                        for m in mem:
                            lines.append(f"  {m}")
                    else:
                        lines.append(
                            f"No prior `seps:memory` issues in {settings.github_memory_repo}."
                        )
                except GhError as exc:
                    if "could not resolve" in str(exc).lower():
                        lines.append(
                            f"Memory: no repo `{settings.github_org}/{settings.github_memory_repo}` yet "
                            "(create it or set SEPS_MEMORY_REPO)."
                        )
                    else:
                        lines.append(f"Memory: could not list issues ({exc}).")
            except GhError as exc:
                lines.append(f"GitHub (gh) org observation failed: {exc}")
        else:
            lines.append(
                "GitHub CLI unavailable or not authenticated; observation limited to local spec only."
            )
        lines.append("Target child repos from config:")
        for s in specs:
            lines.append(f"  - {s['name']}: {s['role']}")
        return {"observation": "\n".join(lines)}

    def plan(state: OrchestratorState) -> dict[str, Any]:
        memory_index = ""
        if org_client:
            try:
                brief = org_client.list_recent_memories(
                    settings.github_memory_repo, limit=10, brief=True
                )
                if brief:
                    memory_index = "\n\nRecent memory issues (read GitHub for full bodies):\n" + "\n".join(
                        f"  {row}" for row in brief
                    )
            except GhError:
                memory_index = ""

        if not llm:
            first = next(
                (s["name"] for s in specs if s["name"] == "agent-marketplace"),
                specs[0]["name"] if specs else "agent-marketplace",
            )
            plan_text = (
                f"No LLM configured. Heuristic: prefer creating `{first}` next. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY for LLM planning.\n"
                f"NEXT_REPO: {first}"
            )
            return {"plan": plan_text}

        spec_blob = json.dumps(specs, indent=2)
        sys = SystemMessage(
            content=(
                "You are the SEPS orchestrator planner for an agent-native marketplace: "
                "tasks are funded in SOL by sponsor agents; executor agents negotiate; "
                "the winning executor receives payout and must deliver for those sponsors. "
                "GitHub (issues labeled seps:task) is the coordination plane; Solana holds escrow/settlement. "
                "Prior orchestrator ticks are stored as GitHub Issues labeled seps:memory — use them as continuity "
                "when the observation summary references them. "
                "Given the observation, pick exactly ONE next concrete step (repo, program, or task flow). "
                "Reply with 2-4 short sentences, then a final line exactly: "
                "NEXT_REPO: <repo_name> from the configured child repo list, or NONE."
            )
        )
        human = HumanMessage(
            content=(
                f"Configured repos:\n{spec_blob}\n\nObservation:\n{state['observation']}"
                f"{memory_index}"
            )
        )
        out = llm.invoke([sys, human])
        text = out.content if isinstance(out.content, str) else str(out.content)
        return {"plan": text}

    def act(state: OrchestratorState) -> dict[str, Any]:
        plan_text = state["plan"]
        repo_name: str | None = None
        for line in plan_text.splitlines():
            if line.strip().upper().startswith("NEXT_REPO:"):
                raw = line.split(":", 1)[1].strip()
                repo_name = None if raw.upper() == "NONE" else raw
                break

        if not repo_name:
            return {"action_taken": "No NEXT_REPO in plan; no GitHub mutation."}

        spec = next((s for s in specs if s["name"] == repo_name), None)
        description = spec["role"] if spec else "SEPS child repo"

        if not org_client:
            return {
                "action_taken": f"Would act on {repo_name} but gh is not available or not logged in.",
                "errors": state.get("errors", []) + ["missing_gh_auth"],
            }

        msg = org_client.ensure_repo_exists(
            repo_name, description, dry_run=state["dry_run"]
        )
        return {"action_taken": msg}

    def remember(state: OrchestratorState) -> dict[str, Any]:
        if not org_client:
            return {"memory_note": "Skipped memory issue: gh not available."}
        title = tick_title()
        body = format_memory_body(
            observation=state["observation"],
            plan=state["plan"],
            action_taken=state["action_taken"],
            dry_run=state["dry_run"],
            errors=state.get("errors"),
        )
        try:
            msg = org_client.create_memory_issue(
                settings.github_memory_repo,
                title,
                body,
                dry_run=state["dry_run"],
            )
            return {"memory_note": msg}
        except GhError as exc:
            return {
                "memory_note": f"Memory write failed: {exc}",
                "errors": state.get("errors", []) + ["memory_write_failed"],
            }

    graph = StateGraph(OrchestratorState)
    graph.add_node("observe", observe)
    graph.add_node("plan", plan)
    graph.add_node("act", act)
    graph.add_node("remember", remember)
    graph.set_entry_point("observe")
    graph.add_edge("observe", "plan")
    graph.add_edge("plan", "act")
    graph.add_edge("act", "remember")
    graph.add_edge("remember", END)
    return graph.compile()
