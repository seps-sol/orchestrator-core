# SEPS — Orchestrator Core

**[seps-sol](https://github.com/seps-sol)** is an **agent-native** swarm: coordination on **GitHub** (Issues + Actions + `gh`), durable **issue-backed memory**, **cross-repo CI chains**, and a path to **Solana** for agent payments (see [PRD](orchestrator/README.md)).

This repository is the **parent orchestrator**: it runs the full **LangGraph** loop, **bootstraps** child repos, and publishes the **org profile** for [`seps-sol/.github`](https://github.com/seps-sol/.github).

---

## What we’re up to (architecture)

```mermaid
flowchart LR
  subgraph parent [orchestrator-core]
    O[observe / plan / act / remember]
    O --> GH[gh CLI]
    O --> Mem[seps:memory Issues]
    Boot[bootstrap workflows]
    Disp[dispatch_downstream]
  end
  subgraph child [each child repo]
    P[pulse + dispatch]
    R[reusable seps-child-orchestrate]
    R --> C[seps once CHILD_TICK_ONLY]
    C --> Mem2[seps:memory in this repo]
  end
  parent --> Boot
  Boot --> child
  Disp -->|seps_upstream| child
```

| Mode | Where | `seps once` behavior |
|------|--------|----------------------|
| **Parent** | This repo’s CI / your laptop | Full loop: org observation, LLM plan, **`gh repo create`** for `NEXT_REPO`, **remember** → `SEPS_MEMORY_REPO` (default **this** repo). |
| **Child** | Reusable [`.github/workflows/seps-child-orchestrate.yml`](.github/workflows/seps-child-orchestrate.yml) | **`SEPS_CHILD_TICK_ONLY`**: same loop but **no org repo creation**; memory + tasks scoped to **that child** via `SEPS_MEMORY_REPO` / `SEPS_TASKS_REPO`. |

**Issue labels:** **`seps:task`** (work board), **`seps:memory`** (tick log).  
**Cross-repo CI:** [`config/ci_triggers.json`](config/ci_triggers.json) + **`repository_dispatch`** event **`seps_upstream`**.  
**Child workflow file:** pushed from [`src/seps/child_self_run.workflow.yml`](src/seps/child_self_run.workflow.yml) by [`uv run seps bootstrap workflows`](src/seps/bootstrap.py).

---

## Prerequisites

- [GitHub CLI](https://cli.github.com/) (`gh`) — **all** GitHub mutations go through `gh`, not the REST SDK.
- Auth: `gh auth login` **or** `GITHUB_TOKEN` / `GH_TOKEN` in `.env`.

## Quickstart

```bash
cd /path/to/orchestrator-core
cp .env.example .env   # set GITHUB_ORG, OPENAI_API_KEY or ANTHROPIC_API_KEY, optional GITHUB_TOKEN
uv sync
uv run seps once                    # full parent tick
uv run seps once --dry-run          # no repo create / no memory write
uv run seps tasks list              # open seps:task issues
uv run seps memory list             # recent seps:memory issues
uv run seps bootstrap workflows     # sync child workflows + baked triggers
```

Org landing copy (GitHub profile) is edited in [`.github-org-readme/profile/README.md`](.github-org-readme/profile/README.md) and published with:

```bash
./scripts/publish_org_profile.sh
```

---

## GitHub Actions (parent workflow)

[`.github/workflows/orchestrator.yml`](.github/workflows/orchestrator.yml) — **schedule `*/5 * * * *`** (GitHub’s minimum; not every 2 min), **`workflow_dispatch`**, **`repository_dispatch`** (`orchestrator_tick`, `seps_upstream`).

Each run (simplified): **pull all org repos** → **`seps once`** → **`seps bootstrap workflows`** → **`dispatch_downstream.sh`** (orchestrator’s row in `ci_triggers.json`) → **publish org profile**.

**Secrets**

| Secret | Where | Why |
|--------|--------|-----|
| **`SEPS_GITHUB_TOKEN`** | **orchestrator-core** | Classic **`repo`** PAT: create org repos, push workflows to children, dispatch, update **`org/.github`**. Default `GITHUB_TOKEN` cannot do this across repos. |
| **`SEPS_CROSS_REPO_TOKEN`** | **each child** (optional) | PAT with **`repo`** so the child workflow can **`repository_dispatch`** to downstream repos. Without it, pulse still runs; **downstream dispatch is skipped**. |
| **`OPENAI_API_KEY`** / **`ANTHROPIC_API_KEY`** | parent + optionally each child | LLM planning; children only need this if you want LLM in **child** ticks. |

**Faster than 5 minutes:** use an external cron hitting [`repository_dispatch`](https://docs.github.com/en/rest/repos/repos#create-a-repository-dispatch-event) with `event_type: orchestrator_tick` (see older README section or GitHub docs).

---

## Layout

| Path | Role |
|------|------|
| `src/seps/graph.py` | LangGraph: observe → plan → act → remember |
| `src/seps/gh_cli.py` / `github_client.py` | `gh` subprocess + org helpers |
| `src/seps/bootstrap.py` | Renders + pushes child `seps-self-run.yml` |
| `src/seps/child_self_run.workflow.yml` | Child template (schedule, dispatch, reusable orchestrate) |
| `.github/workflows/seps-child-orchestrate.yml` | Reusable: checkout this repo, `uv run seps once` with child env |
| `config/child_repos.json` | Repo names the parent can plan / bootstrap |
| `config/ci_triggers.json` | Downstream list per repo for `seps_upstream` |
| `scripts/pull_org_repos.sh` | Shallow pull/clone all org repos on the runner |
| `scripts/dispatch_downstream.sh` | Dispatches from `ci_triggers.json` |
| `scripts/publish_org_profile.sh` | Syncs profile to `ORG/.github` |
| `.github-org-readme/profile/README.md` | **Org** README source |
| `orchestrator/README.md` | Full PRD |

---

**Product spec:** [orchestrator/README.md](orchestrator/README.md)
