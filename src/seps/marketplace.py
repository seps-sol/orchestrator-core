from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TaskStatus = Literal["open", "negotiating", "awarded", "executing", "settled", "canceled"]


@dataclass(frozen=True)
class AgentRef:
    """Agent identity: off-chain handle and optional Solana signer."""

    id: str
    solana_pubkey: str | None = None


@dataclass
class TaskSpec:
    """
    A unit of work funded by agents (SOL), not end users.

    Sponsors lock or delegate bounty; executors compete; the winner is paid
    and must deliver artifacts for those sponsors.
    """

    task_id: str
    description: str
    bounty_lamports: int
    sponsors: list[AgentRef] = field(default_factory=list)
    status: TaskStatus = "open"


@dataclass
class Bid:
    """Executor offer: price and execution plan text (e.g. for LLM + on-chain audit)."""

    agent: AgentRef
    price_lamports: int
    proposal: str


@dataclass
class NegotiationOutcome:
    winner: AgentRef | None
    winning_bid_lamports: int
    status: Literal["no_consensus", "awarded"]
    notes: str = ""


def settle_negotiation(
    bids: list[Bid],
    *,
    max_price_lamports: int | None = None,
) -> NegotiationOutcome:
    """
    Deterministic v0: lowest compliant bid wins if under max price.

    Replace with multi-round LLM negotiation + GitHub thread + escrow proofs later.
    """
    eligible = list(bids)
    if max_price_lamports is not None:
        eligible = [b for b in bids if b.price_lamports <= max_price_lamports]
    if not eligible:
        return NegotiationOutcome(
            winner=None,
            winning_bid_lamports=0,
            status="no_consensus",
            notes="No bids within sponsor budget.",
        )
    best = min(eligible, key=lambda b: b.price_lamports)
    return NegotiationOutcome(
        winner=best.agent,
        winning_bid_lamports=best.price_lamports,
        status="awarded",
        notes="Lowest eligible bid wins (v0 rule).",
    )
