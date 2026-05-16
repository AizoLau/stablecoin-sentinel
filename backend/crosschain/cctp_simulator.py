"""CCTP cross-chain inflow simulator.

Real Circle CCTP burn-and-mint requires the canonical USDC contract; on testnet we
cannot control USDC's mint authority. Instead we simulate the *signal* of a CCTP
inflow by injecting structured sanctions-tag context that marks the recipient as
having received USDC from a cross-chain source (e.g. Ethereum mainnet) with prior
mixer / illicit activity history.

The Risk Sentinel pipeline then treats this exactly like an on-Arc transfer where
the recipient has cross-chain taint — invoking HKMA Para 6.40-6.42 (cross-border
unhosted-wallet rules) and Cap 656 cross-chain provisions, in addition to the
standard Para 5.10(c) freeze logic.

In a production deployment this module would be replaced by a real listener on
the Circle CCTP MessageTransmitter contract; the upstream agent contract — Risk
Assessor + Compliance Decider + Reporter — does not need to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# https://developers.circle.com/stablecoins/cctp-protocol-contract  (domain IDs)
CCTPSourceChain = Literal["ethereum", "arbitrum", "base", "avalanche", "polygon"]

CCTP_DOMAIN_IDS: dict[CCTPSourceChain, int] = {
    "ethereum":  0,
    "avalanche": 1,
    "arbitrum":  3,
    "base":      6,
    "polygon":   7,
}


@dataclass(frozen=True)
class CCTPInflowContext:
    """Marker payload for a simulated CCTP inflow event."""

    source_chain: CCTPSourceChain
    source_domain: int
    source_tx_hash: str   # what the burn tx would have been on the source chain
    recipient: str        # destination wallet on Arc
    amount: int           # raw units, 6 decimals
    risk_tags: tuple[str, ...]


def build_cctp_inflow_context(
    source_chain: CCTPSourceChain,
    recipient: str,
    amount: int = 50_000_000,
) -> CCTPInflowContext:
    """Construct a CCTP inflow context tagged as cross-chain mixer source.

    The tags are designed so the downstream RAG retriever pulls cross-border and
    cross-chain HKMA paragraphs (6.40-6.42) rather than the on-Arc-only freeze
    cluster (5.10-5.12).
    """
    return CCTPInflowContext(
        source_chain=source_chain,
        source_domain=CCTP_DOMAIN_IDS[source_chain],
        source_tx_hash="0x" + "cc" * 32,  # placeholder marker
        recipient=recipient,
        amount=amount,
        risk_tags=(
            f"cross-chain-cctp-inflow-from-{source_chain}",
            "tornado-cash-relay-history",
            "cross-border-designated-party",
        ),
    )
