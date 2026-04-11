# SEPS product steering (read every tick)

**North star:** agents hire agents with SOL — escrow, bids, winner payout, deliverables tied to on-chain state.

## What to optimize each plan for

1. **Ship the marketplace program** (`agent-marketplace`, `protocol-core`): Anchor instructions, PDAs, tests, IDL, and clear issue ↔ account linkage.
2. **Prove it in CI** (`tests-suite`): failing tests are signal; add or fix tests when touching protocol behavior.
3. **Make coordination legible** (`seps:task`): every “yes” on `SEPS_OPEN_TASK` must name a **single shippable slice** another agent or human can execute without guessing.
4. **Child repos** stay in-repo: no inventing new org repos from children; propose code/tests/docs for **this** repository only.

## When to set `SEPS_OPEN_TASK: yes`

Only when **all** hold:

- There is a **concrete next change** (file area, instruction, or test case named).
- It is **not** already covered by an open `seps:task` with the same title (the orchestrator skips duplicates).
- The task fits in **roughly one PR** or one focused session.

Otherwise use `SEPS_OPEN_TASK: no` and rely on `seps:memory` for the tick log.

## Draft PR handoff (`SEPS_EXECUTE`)

When you also set **`SEPS_EXECUTE: yes`** in the same plan footer (only with **`SEPS_OPEN_TASK: yes`**), the orchestrator opens a **draft PR** on the task repo that adds `docs/seps-handoffs/issue-<n>.md` (issue snapshot + optional **`SEPS_EXECUTE_LLM: yes`** outline). That is the default **build bridge**—still not merging product code automatically.

For one-off runs use **`uv run seps execute --repo <short-name> --issue <n>`** or the GitHub Action **“SEPS execute task”** on `orchestrator-core`.
