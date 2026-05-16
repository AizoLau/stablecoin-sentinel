"""ManagerAgent v1 — single-shot Gemini decision over a TransferEvent.

M2 scope: one synchronous LLM call that consumes the transfer event, both addresses'
DeBank profiles, and sanctions registry hits, then returns an Action + paragraph-cited
reasoning.

M3 will split this into RiskAssessor / ComplianceDecider / ExecutorAgent / Reporter
and replace the inline paragraph excerpts with RAG retrieval over Chroma.
"""

from __future__ import annotations

import logging
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from backend.config import Settings
from backend.data.debank_client import AddressProfile, DeBankClient
from backend.data.sanctions import SanctionsHit, SanctionsRegistry
from backend.rag.retrieve import HKMARetriever, RetrievedChunk
from backend.store.models import Action, Decision, TransferEvent

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are the compliance decision agent for a Hong Kong licensed stablecoin issuer. You
monitor USDC P2P transfers between unhosted wallets on Arc Network and decide whether
to PASS, REFUND, QUARANTINE, or FREEZE based on AML/CFT risk.

Each user message includes a "Retrieved HKMA paragraphs" block. You MUST treat that
block as the authoritative regulatory ground truth: every paragraph_id you cite in
`paragraphs_cited` MUST exactly match a paragraph_id present in the retrieved block.
Do not invent paragraph numbers. If the retrieved block does not justify an action,
prefer PASS or escalate to QUARANTINE with reasoning.

Action semantics:
- PASS: low risk, allow the transfer to stand.
- REFUND: medium risk; return the funds to the sender (Para 6.22-6.24).
- QUARANTINE: high risk but recipient may be victim; force-move funds to recovery
  wallet for manual review (Para 6.22-6.24 + 6.40-6.42).
- FREEZE: confirmed sanctions match or strong illicit-activity signal; lock the
  recipient address from any further transfers (Para 5.10(c), 5.11, 7.5).

Decision rules:
- Sanctions registry hit on EITHER address: FREEZE that address.
- DeBank profile shows recipient has multiple scam-flagged historical tx AND no
  prior CDD relationship: prefer QUARANTINE (recipient may be victim of dust) or
  FREEZE (recipient is the perpetrator) — use judgment.
- Recipient with zero history and small transfer: PASS (cold wallet, no signal).
- Always cite specific paragraph numbers in `paragraphs_cited`.
- `target_address` MUST be the address you are acting on (recipient for FREEZE, the
  party receiving the refund/quarantine for REFUND/QUARANTINE, or empty string for PASS).
- `reasoning_md` MUST quote the specific evidence (e.g., "DeBank shows 17 scam tx",
  "Sanctions registry hit: tag=known-mixer source=DEMO-OFAC-001").
"""


class LLMDecisionOutput(BaseModel):
    action: Literal["pass", "refund", "quarantine", "freeze"]
    target_address: str = Field(description="address acted upon; empty string if PASS")
    risk_score: int = Field(ge=0, le=100)
    paragraphs_cited: list[str]
    reasoning_md: str


def _profile_summary(p: AddressProfile, role: str) -> str:
    if not p.is_active():
        return f"- {role} ({p.address}): NO ACTIVITY on any chain (cold/new wallet)."
    return (
        f"- {role} ({p.address}): {p.chains_count} chains used, "
        f"{p.tx_count_recent} recent tx, {p.counterparty_count} unique counterparties, "
        f"scam-flagged tx: {p.scam_tx_count}, total USD value: ${p.total_usd_value:,.0f}."
        + (
            f" Scam counterparties involved: {list(p.scam_counterparties[:3])}"
            if p.scam_counterparties
            else ""
        )
    )


def _sanctions_summary(addr: str, hit: SanctionsHit | None, role: str) -> str:
    if hit is None:
        return f"- {role} ({addr}): no sanctions registry match."
    return (
        f"- {role} ({addr}): SANCTIONS HIT — tags={list(hit.tags)}, "
        f"source={hit.source}, paragraph_ref={hit.paragraph_ref}."
    )


class ManagerAgent:
    def __init__(
        self,
        settings: Settings,
        debank: DeBankClient,
        sanctions: SanctionsRegistry,
        retriever: HKMARetriever,
    ):
        self.settings = settings
        self.debank = debank
        self.sanctions = sanctions
        self.retriever = retriever
        self._gemini = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model_pro

    async def decide(self, transfer: TransferEvent) -> Decision:
        from_profile = await self.debank.get_profile(transfer.from_address)
        to_profile = await self.debank.get_profile(transfer.to_address)
        from_hit = self.sanctions.lookup(transfer.from_address)
        to_hit = self.sanctions.lookup(transfer.to_address)

        retrieved = self._retrieve_paragraphs(
            from_profile, to_profile, from_hit, to_hit
        )

        context = self._build_context(
            transfer, from_profile, to_profile, from_hit, to_hit, retrieved
        )
        logger.info(
            "Calling %s for transfer %s with %d retrieved paragraphs",
            self.model, transfer.tx_hash[:10], len(retrieved),
        )

        resp = self._gemini.models.generate_content(
            model=self.model,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=LLMDecisionOutput,
                temperature=0.2,
            ),
        )
        parsed: LLMDecisionOutput = resp.parsed  # type: ignore[assignment]
        if parsed is None:
            raise RuntimeError(f"Gemini did not return a parseable Decision: {resp.text!r}")

        return Decision(
            transfer=transfer,
            action=Action(parsed.action),
            target_address=parsed.target_address,
            risk_score=parsed.risk_score,
            paragraphs_cited=parsed.paragraphs_cited,
            reasoning_md=parsed.reasoning_md,
        )

    def _retrieve_paragraphs(
        self,
        from_profile: AddressProfile,
        to_profile: AddressProfile,
        from_hit: SanctionsHit | None,
        to_hit: SanctionsHit | None,
    ) -> list[RetrievedChunk]:
        """Build a focused RAG query from the situation and pull top paragraphs."""
        signals = ["unhosted wallet peer-to-peer transfer monitoring"]
        if from_hit or to_hit:
            tags = list((from_hit.tags if from_hit else ()) + (to_hit.tags if to_hit else ()))
            signals.append(f"sanctions screening positive match tags={tags}")
            signals.append("freeze stablecoin designated party")
        if (from_profile and from_profile.has_scam_history()) or (
            to_profile and to_profile.has_scam_history()
        ):
            signals.append("counterparty with scam-flagged transaction history")
        if (from_profile and not from_profile.is_active()) and (
            to_profile and not to_profile.is_active()
        ):
            signals.append("low activity new wallet ongoing monitoring")
        query = "; ".join(signals)
        return self.retriever.retrieve(query, top_k=8)

    def _build_context(
        self,
        transfer: TransferEvent,
        from_profile: AddressProfile,
        to_profile: AddressProfile,
        from_hit: SanctionsHit | None,
        to_hit: SanctionsHit | None,
        retrieved: list[RetrievedChunk],
    ) -> str:
        amount_human = transfer.amount / 1e6
        retrieved_block = "\n".join(
            f"- Para {c.paragraph_id} (sim={c.similarity:.2f}): {c.text[:400]}"
            for c in retrieved
        ) or "  (no relevant paragraphs retrieved)"

        return f"""\
Transfer event observed on Arc Testnet:
- tx_hash: {transfer.tx_hash}
- from: {transfer.from_address}
- to:   {transfer.to_address}
- amount: {amount_human:,.2f} mUSDC ({transfer.amount} raw units)
- block: {transfer.block_number}

Cross-chain DeBank profiles:
{_profile_summary(from_profile, "FROM")}
{_profile_summary(to_profile, "TO  ")}

Sanctions registry lookup:
{_sanctions_summary(transfer.from_address, from_hit, "FROM")}
{_sanctions_summary(transfer.to_address, to_hit, "TO  ")}

Retrieved HKMA paragraphs (authoritative — cite only these IDs):
{retrieved_block}

Decide the action per the system rules. Cite only retrieved paragraph_ids precisely.
"""
