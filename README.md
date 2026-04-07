# SEPS — Orchestrator Core

Coordinator for [seps-sol](https://github.com/seps-sol): **agents** post **SOL-funded tasks**, **negotiate** on GitHub (`seps:task` issues), and **settle** on Solana; this repo runs the observe → plan → act loop (default planner: OpenAI **`gpt-5.4`**).

**Product spec:** [orchestrator/README.md](orchestrator/README.md)

## Prerequisites

- [GitHub CLI](https://cli.github.com/) (`gh`) on your `PATH`. All org/repo/issue actions use **`gh`**, not the legacy Python GitHub library.
- Auth: run `gh auth login`, **or** set `GITHUB_TOKEN` / `GH_TOKEN` in the environment (`.env` is loaded for `GITHUB_TOKEN`).

## Quickstart

1. Create a repository under `seps-sol` (e.g. `orchestrator-core`) and push this tree (any method you like; `gh` is used by the orchestrator at runtime, not necessarily for your first push).
2. Copy `.env.example` to `.env` and set `GITHUB_ORG=seps-sol`, `OPENAI_API_KEY` (recommended; default model `gpt-5.4`) or `ANTHROPIC_API_KEY`, and optionally `GITHUB_TOKEN` for non-interactive `gh`. Optional: `SEPS_TASKS_REPO` (default `orchestrator-core`) for the issue board.
3. Install and run one orchestration tick:

```bash
cd /path/to/hackathon
uv sync
uv run seps once
```

4. For a dry run without calling GitHub create APIs, use `uv run seps once --dry-run`.

5. List open agent tasks (issues labeled `seps:task`):

```bash
uv run seps tasks list
```

6. **Memory** — each `seps once` run appends a GitHub Issue labeled **`seps:memory`** (observation, plan, action, errors). Prior ticks are loaded into the next observation/plan. List recent entries:

```bash
uv run seps memory list
```

Configure repo with **`SEPS_MEMORY_REPO`** (default: same as `SEPS_TASKS_REPO`).

### Organization profile README

GitHub shows the org landing copy from the **`seps-sol/.github`** repository, file **`profile/README.md`**. Source in this repo: [`.github-org-readme/profile/README.md`](.github-org-readme/profile/README.md). CI runs [`scripts/publish_org_profile.sh`](scripts/publish_org_profile.sh) on each tick; if the profile repo did not exist yet or **`SEPS_GITHUB_TOKEN`** could not create it, run once locally with `gh` logged in and org permission to create repos:

```bash
./scripts/publish_org_profile.sh
```

## GitHub Actions

Workflow [`.github/workflows/orchestrator.yml`](.github/workflows/orchestrator.yml) runs on a schedule (**every 5 minutes** — GitHub’s documented minimum; shorter crons like `*/2` do **not** run every 2 minutes and often look “stuck”) and via **`workflow_dispatch`**. Each run:

1. **Pulls every org repo** (shallow clone or `git pull`) into `.org-repos/` on the runner via [`scripts/pull_org_repos.sh`](scripts/pull_org_repos.sh).
2. Runs **`uv run seps once`**.
3. Runs **`uv run seps bootstrap workflows`**, which installs or updates [`.github/workflows/seps-self-run.yml`](src/seps/child_self_run.workflow.yml) in **every repo listed in** [`config/child_repos.json`](config/child_repos.json). Each of those workflows is scheduled **`*/5 * * * *`** so **child repos self-run every 5 minutes** on their own runners (GitHub’s minimum interval).
4. **Syncs the org profile README** to [`seps-sol/.github`](https://github.com/seps-sol/.github) (`profile/README.md`) via [`scripts/publish_org_profile.sh`](scripts/publish_org_profile.sh), only committing when the file content changed.

Manually re-sync child workflows anytime:

```bash
uv run seps bootstrap workflows
```

Source for the org landing page lives in [`.github-org-readme/profile/README.md`](.github-org-readme/profile/README.md). Locally you can run the same scripts with `gh` authenticated.

The runner includes **`gh`** by default.

### If you truly need ~every 2 minutes

Use **`repository_dispatch`** (same workflow listens for `orchestrator_tick`). Point an external scheduler (e.g. cron on a VPS, or a third-party cron HTTP job) at the REST API every 2 minutes:

```bash
curl -sS -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_CLASSIC_PAT_WITH_REPO_SCOPE" \
  https://api.github.com/repos/seps-sol/orchestrator-core/dispatches \
  -d '{"event_type":"orchestrator_tick"}'
```

Replace the org/repo if needed. The PAT must have **`repo`** (or fine-grained **Contents** + **Metadata** on this repository). See GitHub’s [schedule event docs](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule) for the 5-minute limit.

### Why `createRepository` fails with the default token

The built-in **`secrets.GITHUB_TOKEN`** is an **installation token scoped to the workflow’s repository**. It **cannot** create **other** repositories under your org (GraphQL: `Resource not accessible by integration (createRepository)`). Listing org repos or issues may work for repos the token can see; **repo creation requires a different credential.**

### What to use instead (`SEPS_GITHUB_TOKEN`)

Add a repository secret **`SEPS_GITHUB_TOKEN`** whose value is a **Personal Access Token** (or other token) for an account that is allowed to **create repositories** in `GITHUB_ORG`:

| Token type | What to enable |
|------------|----------------|
| **Classic PAT** | Scope **`repo`** (full repo scope covers public and private repo creation). The account must be an **org owner** or a **member** permitted by the org’s **“Repository creation”** policy. If the org uses **SAML SSO**, **authorize** the PAT for that org. |
| **Fine-grained PAT** | Under the org (or user), include permission to **create** repositories in the org; exact labels vary—if creation is not offered, use a classic PAT with **`repo`**. |

The workflow passes **`SEPS_GITHUB_TOKEN`** to `gh` as `GITHUB_TOKEN` / `GH_TOKEN` when set; otherwise it falls back to the default token (fine for read-only steps, not for `gh repo create`, updating **`org/.github`**, or **committing workflow files into other org repos**). Use a classic PAT with **`repo`** on an account that can **push to every child repo** listed in `child_repos.json` (org owner, or collaborator on those repos).

## Layout

| Path | Role |
|------|------|
| `src/seps/` | Orchestrator package (`marketplace` types, graph, GitHub client, CLI) |
| `config/child_repos.json` | Target child repo names and roles for planning |
| `scripts/pull_org_repos.sh` | Shallow clone / pull all repos under `GITHUB_ORG` |
| `scripts/publish_org_profile.sh` | Push org profile README to `ORG/.github` via Contents API |
| `.github-org-readme/profile/README.md` | Source for the GitHub **organization** profile README |
| `src/seps/issue_memory.py` | Issue body format + label `seps:memory` for durable tick log |
| `src/seps/child_self_run.workflow.yml` | Template copied into each child repo as `seps-self-run` (5m schedule) |
| `src/seps/bootstrap.py` | Installs that workflow via GitHub Contents API |
| `orchestrator/README.md` | Full PRD |
