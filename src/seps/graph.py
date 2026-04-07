from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from seps.config import Settings
from seps.github_client import OrgClient, load_child_repo_spec
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
            repos = org_client.list_public_repo_names()
            lines.append(f"Org repos ({len(repos)}): {', '.join(repos) or '(none)'}")
        else:
            lines.append("No GITHUB_TOKEN; observation limited to local spec only.")
        lines.append("Target child repos from config:")
        for s in specs:
            lines.append(f"  - {s['name']}: {s['role']}")
        return {"observation": "\n".join(lines)}

    def plan(state: OrchestratorState) -> dict[str, Any]:
        if not llm:
            first = specs[0]["name"] if specs else "protocol-core"
            plan_text = (
                f"No LLM configured. Heuristic: prefer creating `{first}` next. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY for LLM planning.\n"
                f"NEXT_REPO: {first}"
            )
            return {"plan": plan_text}

        spec_blob = json.dumps(specs, indent=2)
        sys = SystemMessage(
            content=(
                "You are the SEPS orchestrator planner. Given the observation, "
                "pick exactly ONE next concrete step for a GitHub org building a Solana protocol swarm. "
                "Reply with 2-4 short sentences. End with a single line: "
                "NEXT_REPO: <repo_name> where repo_name is one of the configured child repo names, "
                "or NONE if only meta-work is needed."
            )
        )
        human = HumanMessage(
            content=f"Configured repos:\n{spec_blob}\n\nObservation:\n{state['observation']}"
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
                "action_taken": f"Would act on {repo_name} but GITHUB_TOKEN missing.",
                "errors": state.get("errors", []) + ["missing_github_token"],
            }

        msg = org_client.ensure_repo_exists(
            repo_name, description, dry_run=state["dry_run"]
        )
        return {"action_taken": msg}

    graph = StateGraph(OrchestratorState)
    graph.add_node("observe", observe)
    graph.add_node("plan", plan)
    graph.add_node("act", act)
    graph.set_entry_point("observe")
    graph.add_edge("observe", "plan")
    graph.add_edge("plan", "act")
    graph.add_edge("act", END)
    return graph.compile()
