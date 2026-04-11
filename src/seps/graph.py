from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from seps.config import Settings
from seps.execute_task import run_execute_issue
from seps.gh_cli import GhError
from seps.github_client import OrgClient, load_child_repo_spec
from seps.issue_memory import format_memory_body, tick_title
from seps.llm import get_chat_model
from seps.plan_parse import parse_plan_directives
from seps.state import OrchestratorState
from seps.steering_context import load_steering_context

_PLAN_FOOTER = """
After your prose, end with exactly these machine-parseable lines (one key per line, first colon separates key from value):
NEXT_REPO: NONE | <repo_name from configured child list>  (orchestrator only — in child mode must be NONE)
SEPS_OPEN_TASK: no | yes
SEPS_TASK_TITLE: NONE | <short imperative title>
SEPS_TASK_DETAIL: NONE | <one line acceptance criteria / definition of done>
SEPS_TASK_REPO: NONE | <repo_name>  (GitHub repo for the new issue; NONE = default task board from environment)
SEPS_EXECUTE: no | yes  (only after SEPS_OPEN_TASK: yes — opens a draft PR with a handoff doc on the task repo)
SEPS_EXECUTE_LLM: no | yes  (optional outline in the handoff doc; uses API spend)

Rules: Use SEPS_OPEN_TASK: yes only for a single shippable slice that fits roughly one PR. Use SEPS_EXECUTE: yes sparingly (token must allow push + pull-requests on the task repo). Use NONE for unused fields. In child mode, NEXT_REPO must be NONE and SEPS_TASK_REPO must be NONE (tasks open only on this repository).
""".strip()


@dataclass
class SteeredTaskOutcome:
    message: str
    issue_number: int | None = None
    task_repo: str | None = None


def _truthy_directive(value: str | None) -> bool:
    return (value or "").strip().lower() in ("yes", "y", "true", "1")


def _next_repo_name(plan_text: str, directives: dict[str, str]) -> str | None:
    raw = directives.get("NEXT_REPO")
    if raw is not None:
        val = raw.strip()
        return None if not val or val.upper() == "NONE" else val
    for line in plan_text.splitlines():
        if line.strip().upper().startswith("NEXT_REPO:"):
            v = line.split(":", 1)[1].strip()
            return None if not v or v.upper() == "NONE" else v
    return None


def _allowed_task_repo_names(settings: Settings, specs: list[dict[str, Any]]) -> set[str]:
    names = {str(s["name"]) for s in specs}
    names.add(settings.github_tasks_repo)
    names.add(settings.github_memory_repo)
    return names


def _run_steered_task(
    *,
    org_client: OrgClient | None,
    settings: Settings,
    directives: dict[str, str],
    dry_run: bool,
    specs: list[dict[str, Any]],
    child: bool,
) -> SteeredTaskOutcome:
    """Create optional `seps:task` from planner directives."""
    if not org_client:
        return SteeredTaskOutcome("")

    if not _truthy_directive(directives.get("SEPS_OPEN_TASK")):
        return SteeredTaskOutcome("")

    title = directives.get("SEPS_TASK_TITLE", "").strip()
    if not title or title.upper() == "NONE":
        return SteeredTaskOutcome(
            "SEPS_OPEN_TASK yes but missing SEPS_TASK_TITLE; skipped task create."
        )

    detail = directives.get("SEPS_TASK_DETAIL", "").strip()
    if detail.upper() == "NONE":
        detail = ""

    allowed = _allowed_task_repo_names(settings, specs)
    notes: list[str] = []

    if child:
        task_repo = settings.github_tasks_repo
        tr = directives.get("SEPS_TASK_REPO", "").strip()
        if tr and tr.upper() != "NONE" and tr != task_repo:
            notes.append(
                f"Ignored SEPS_TASK_REPO={tr!r} (child tick tasks only on {task_repo})."
            )
    else:
        tr = directives.get("SEPS_TASK_REPO", "").strip()
        if not tr or tr.upper() == "NONE":
            task_repo = settings.github_tasks_repo
        elif tr in allowed:
            task_repo = tr
        else:
            return SteeredTaskOutcome(
                f"Invalid SEPS_TASK_REPO {tr!r} (allowed: {', '.join(sorted(allowed))}); "
                "skipped task create."
            )

    if title.strip().lower() in org_client.open_task_titles_lower(task_repo):
        notes.append(
            f"Open task already exists with title {title!r} on {task_repo}; skipped."
        )
        return SteeredTaskOutcome(" ".join(notes) if notes else "")

    body = "## Steered task (orchestrator tick)\n\n"
    if detail:
        body += f"**Acceptance:** {detail}\n\n"
    body += "_Created from planner directives (`SEPS_OPEN_TASK: yes`). Close when done._\n"

    try:
        msg, issue_num = org_client.create_task_issue(
            task_repo, title, body, dry_run=dry_run
        )
    except GhError as exc:
        return SteeredTaskOutcome(f"Task create failed: {exc}")

    if notes:
        msg = f"{' '.join(notes)} {msg}".strip()
    return SteeredTaskOutcome(msg, issue_num, task_repo)


def build_graph(settings: Settings) -> StateGraph:
    specs = load_child_repo_spec(settings.repo_root)
    org_client: OrgClient | None
    try:
        org_client = OrgClient(settings)
    except ValueError:
        org_client = None
    llm = get_chat_model(settings)
    child = settings.child_tick_only()
    steering_block = load_steering_context(settings.repo_root)
    steering_inject = (
        f"## Product steering (from config/steering.md)\n\n{steering_block}\n\n"
        if steering_block
        else ""
    )

    def observe(state: OrchestratorState) -> dict[str, Any]:
        lines: list[str] = []
        if org_client:
            try:
                if child:
                    lines.append(
                        f"Child tick (`SEPS_CHILD_TICK_ONLY`): this run is scoped to "
                        f"`{settings.github_org}/{settings.github_tasks_repo}` "
                        "(Issues memory/tasks); org-wide repo listing is skipped."
                    )
                else:
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
                lines.append(f"GitHub (gh) observation failed: {exc}")
        else:
            lines.append(
                "GitHub CLI unavailable or not authenticated; observation limited to local spec only."
            )
        if not child:
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

        if child:
            if not llm:
                return {
                    "plan": (
                        "Child tick: no LLM configured; no org-level mutations.\n"
                        "NEXT_REPO: NONE\n"
                        "SEPS_OPEN_TASK: no\n"
                        "SEPS_TASK_TITLE: NONE\n"
                        "SEPS_TASK_DETAIL: NONE\n"
                        "SEPS_TASK_REPO: NONE\n"
                        "SEPS_EXECUTE: no\n"
                        "SEPS_EXECUTE_LLM: no"
                    )
                }
            sys = SystemMessage(
                content=(
                    "You are a SEPS agent in CHILD_TICK_ONLY mode for one repository. "
                    "Use observation, tasks (seps:task), and memory (seps:memory) for context. "
                    "Propose concrete next steps for THIS repo only (code, tests, docs). "
                    "Do not plan creating other org repos — that is orchestrator-core only. "
                    "Steer work toward the Solana marketplace + escrow outcomes described in steering. "
                    f"{_PLAN_FOOTER}"
                )
            )
            human = HumanMessage(
                content=(
                    f"{steering_inject}"
                    f"Observation:\n{state['observation']}{memory_index}"
                )
            )
            out = llm.invoke([sys, human])
            text = out.content if isinstance(out.content, str) else str(out.content)
            return {"plan": text}

        if not llm:
            first = next(
                (s["name"] for s in specs if s["name"] == "agent-marketplace"),
                specs[0]["name"] if specs else "agent-marketplace",
            )
            plan_text = (
                f"No LLM configured. Heuristic: prefer creating `{first}` next. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY for LLM planning.\n"
                f"NEXT_REPO: {first}\n"
                "SEPS_OPEN_TASK: no\n"
                "SEPS_TASK_TITLE: NONE\n"
                "SEPS_TASK_DETAIL: NONE\n"
                "SEPS_TASK_REPO: NONE\n"
                "SEPS_EXECUTE: no\n"
                "SEPS_EXECUTE_LLM: no"
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
                "You may open a new steered task issue only when SEPS_OPEN_TASK: yes and the title/detail are "
                "specific enough for another agent to execute without guessing. "
                f"{_PLAN_FOOTER}"
            )
        )
        human = HumanMessage(
            content=(
                f"{steering_inject}"
                f"Configured repos:\n{spec_blob}\n\nObservation:\n{state['observation']}"
                f"{memory_index}"
            )
        )
        out = llm.invoke([sys, human])
        text = out.content if isinstance(out.content, str) else str(out.content)
        return {"plan": text}

    def act(state: OrchestratorState) -> dict[str, Any]:
        plan_text = state["plan"]
        directives = parse_plan_directives(plan_text)
        parts: list[str] = []

        if child:
            parts.append(
                "Child tick: skipped org-level repo creation (SEPS_CHILD_TICK_ONLY)."
            )
        else:
            repo_name = _next_repo_name(plan_text, directives)
            if repo_name:
                spec = next((s for s in specs if s["name"] == repo_name), None)
                description = spec["role"] if spec else "SEPS child repo"
                if not org_client:
                    parts.append(
                        f"Would ensure repo {repo_name} but gh is not available or not logged in."
                    )
                    err = state.get("errors", []) + ["missing_gh_auth"]
                    task_out = _run_steered_task(
                        org_client=None,
                        settings=settings,
                        directives=directives,
                        dry_run=state["dry_run"],
                        specs=specs,
                        child=False,
                    )
                    if task_out.message:
                        parts.append(task_out.message)
                    return {"action_taken": " ".join(parts), "errors": err}
                msg = org_client.ensure_repo_exists(
                    repo_name, description, dry_run=state["dry_run"]
                )
                parts.append(msg)
            else:
                parts.append("No NEXT_REPO in plan; no repo create.")

        task_out = _run_steered_task(
            org_client=org_client,
            settings=settings,
            directives=directives,
            dry_run=state["dry_run"],
            specs=specs,
            child=child,
        )
        if task_out.message:
            parts.append(task_out.message)

        if (
            org_client
            and _truthy_directive(directives.get("SEPS_EXECUTE"))
            and task_out.issue_number is not None
            and task_out.task_repo
        ):
            if state["dry_run"]:
                parts.append(
                    "[dry-run] would run seps execute "
                    f"--repo {task_out.task_repo} --issue {task_out.issue_number}"
                )
            else:
                try:
                    parts.append(
                        run_execute_issue(
                            settings,
                            task_out.task_repo,
                            task_out.issue_number,
                            dry_run=False,
                            with_llm=_truthy_directive(
                                directives.get("SEPS_EXECUTE_LLM")
                            ),
                        )
                    )
                except GhError as exc:
                    parts.append(f"Execute failed: {exc}")

        return {"action_taken": " ".join(parts)}

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
