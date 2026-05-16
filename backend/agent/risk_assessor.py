"""RiskAssessor sub-agent — assesses a P2P transfer's wallets and emits a RiskProfile.

Anchored on HKMA AML/CFT Guideline Para 4.39 (screening), 5.4 (risk-based ongoing
monitoring scope). Consumes the DeBank cross-chain profile and any sanctions match
to produce a structured risk profile that the ComplianceDecider consumes downstream.

The RiskAssessor is intentionally light on regulatory citation work — that is the
ComplianceDecider's job. Its output is a risk *characterization*, not an action.
"""

from __future__ import annotations

import logging

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from backend.config import Settings
from backend.data.debank_client import AddressProfile
from backend.data.sanctions import SanctionsHit
from backend.store.models import TransferEvent

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are the Risk Assessor agent for a Hong Kong licensed stablecoin issuer monitoring
USDC transfers between unhosted wallets on Arc Network.

Anchor regulations:
- HKMA AML/CFT Guideline Para 4.39: licensees must screen unhosted-wallet addresses for
  direct or indirect association with illicit/suspicious activities or designated parties.
- HKMA AML/CFT Guideline Para 5.4: ongoing monitoring scope must be commensurate with
  the ML/TF risk level.

You receive the transfer event, cross-chain DeBank profiles for both addresses, and any
sanctions-list lookup results. Output a structured RiskProfile:

- score (0-100): integer overall risk score. Use these anchors:
    - 0-19: clean, both addresses with no adverse signals
    - 20-49: mild signal (low activity, fresh wallet, minor scam flag)
    - 50-79: moderate concern (multiple scam-flagged tx, suspicious cross-chain pattern)
    - 80-100: severe (sanctions hit, designated party, confirmed mixer)
- flags: short snake_case strings describing the concerns (e.g. "sanctions_match",
  "mixer_tag", "low_activity", "cross_chain_taint", "high_scam_tx_count"). Empty if clean.
- cross_chain_summary: one-paragraph narrative of the address's footprint (chains used,
  notable counterparties, scam history).
- primary_concerns: bullet-style list of the top 1-3 reasons this transfer warrants
  scrutiny. Empty if score < 20.

Do NOT prescribe an action — that is the ComplianceDecider's responsibility.
"""


class RiskProfileOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    flags: list[str] = Field(default_factory=list)
    cross_chain_summary: str = ""
    primary_concerns: list[str] = Field(default_factory=list)


def _profile_block(p: AddressProfile, role: str) -> str:
    if not p.is_active():
        return f"- {role} ({p.address}): no activity on any chain (cold/new wallet)."
    return (
        f"- {role} ({p.address}): {p.chains_count} chains used; "
        f"{p.tx_count_recent} recent tx; {p.counterparty_count} counterparties; "
        f"{p.scam_tx_count} scam-flagged tx; total USD ${p.total_usd_value:,.0f}."
        + (f" Scam counterparties: {list(p.scam_counterparties[:3])}" if p.scam_counterparties else "")
    )


def _sanctions_block(addr: str, hit: SanctionsHit | None, role: str) -> str:
    if hit is None:
        return f"- {role} ({addr}): no sanctions match."
    return (
        f"- {role} ({addr}): SANCTIONS HIT — tags={list(hit.tags)}, source={hit.source}."
    )


class RiskAssessor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._gemini = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model_flash

    def assess(
        self,
        transfer: TransferEvent,
        from_profile: AddressProfile,
        to_profile: AddressProfile,
        from_hit: SanctionsHit | None,
        to_hit: SanctionsHit | None,
    ) -> RiskProfileOutput:
        amount_human = transfer.amount / 1e6
        context = f"""\
Transfer:
- amount: {amount_human:,.2f} mUSDC ({transfer.amount} raw)
- from -> to: {transfer.from_address} -> {transfer.to_address}

DeBank cross-chain profiles:
{_profile_block(from_profile, "FROM")}
{_profile_block(to_profile, "TO  ")}

Sanctions screening:
{_sanctions_block(transfer.from_address, from_hit, "FROM")}
{_sanctions_block(transfer.to_address, to_hit, "TO  ")}

Emit a RiskProfile per the system rules.
"""
        logger.info("RiskAssessor: invoking %s", self.model)
        resp = self._gemini.models.generate_content(
            model=self.model,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=RiskProfileOutput,
                temperature=0.2,
            ),
        )
        out: RiskProfileOutput | None = resp.parsed  # type: ignore[assignment]
        if out is None:
            raise RuntimeError(f"RiskAssessor returned no parsed output: {resp.text!r}")
        return out
