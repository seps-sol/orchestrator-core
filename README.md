# SEPS — Orchestrator Core

Central coordinator for the [seps-sol](https://github.com/seps-sol) organization: observe the org, plan the next step with an LLM, and act via the GitHub API (repo creation, issues, PR hooks). Solana deploy and child-repo codegen come next.

**Product spec:** [orchestrator/README.md](orchestrator/README.md)

## Quickstart

1. Create a repository under `seps-sol` (e.g. `orchestrator-core`) and push this tree.
2. Copy `.env.example` to `.env` and set `GITHUB_TOKEN`, `GITHUB_ORG=seps-sol`, and an LLM key (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`).
3. Install and run one orchestration tick:

```bash
cd /path/to/hackathon
uv sync
uv run seps once
```

4. For a dry run without calling GitHub create APIs, use `uv run seps once --dry-run`.

## GitHub Actions

Workflow [`.github/workflows/orchestrator.yml`](.github/workflows/orchestrator.yml) runs on a schedule (every 10 minutes) and via `workflow_dispatch`. Add repo secrets: `GITHUB_TOKEN` is provided automatically as `secrets.GITHUB_TOKEN` for same-repo operations; for **creating repos in the org**, use a PAT or GitHub App token with `repo` and `admin:org` (or scoped equivalent) stored as a secret (e.g. `SEPS_GITHUB_TOKEN`).

## Layout

| Path | Role |
|------|------|
| `src/seps/` | Orchestrator package (graph, GitHub client, CLI) |
| `config/child_repos.json` | Target child repo names and roles for planning |
| `orchestrator/README.md` | Full PRD |
