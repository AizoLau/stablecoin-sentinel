"""ManagerAgent — orchestrates the four sub-agents through the decision pipeline.

The Manager is intentionally NOT itself an LLM. Splitting orchestration out of
LLM-driven reasoning keeps the control flow auditable and makes each sub-agent's
contract testable in isolation. Pipeline:

    TransferEvent
       └── fetch DeBank profiles + sanctions lookups
       └── RAG.retrieve(top-K HKMA / Cap 656 paragraphs)
       └── RiskAssessor.assess()       -> RiskProfile
       └── ComplianceDecider.decide()  -> Action + cited paragraphs
       └── Reporter.report()           -> markdown XAI justification
       └── Manager assembles Decision
       (Executor downstream submits on-chain via Circle Wallets MPC)
"""

from __future__ import annotations

import logging
import re

from backend.agent.compliance_decider import ComplianceDecider
from backend.agent.reporter import Reporter
from backend.agent.risk_assessor import RiskAssessor, RiskProfileOutput
from backend.config import Settings
from backend.data.debank_client import AddressProfile, DeBankClient
from backend.data.sanctions import SanctionsHit, SanctionsRegistry
from backend.rag.retrieve import HKMARetriever, RetrievedChunk
from backend.store.models import Action, Decision, TransferEvent

logger = logging.getLogger(__name__)


_CITATION_PREFIX = re.compile(r"^\s*(?:para(?:graph)?|section|sec\.?|§)\s+", re.IGNORECASE)


def _normalize_paragraph_id(raw: str) -> str:
    """Strip prefixes like "Para ", "Section ", "§ " so audit IDs match retrieved IDs."""
    return _CITATION_PREFIX.sub("", raw).strip()


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
        self.risk_assessor = RiskAssessor(settings)
        self.decider = ComplianceDecider(settings)
        self.reporter = Reporter(settings)

    async def decide(self, transfer: TransferEvent) -> tuple[Decision, list[RetrievedChunk]]:
        """Run the LLM pipeline; on Gemini outage fall back to a deterministic rule engine.

        The fallback path guarantees that a clear sanctions match still produces a FREEZE
        even if every Gemini call 429s — this is the audit-defensible behavior.
        """
        try:
            return await self._decide_with_llm(transfer)
        except Exception as exc:
            logger.exception("LLM pipeline failed; engaging rule-engine fallback: %s", exc)
            from_hit = self.sanctions.lookup(transfer.from_address)
            to_hit = self.sanctions.lookup(transfer.to_address)
            return self._fallback_decision(transfer, from_hit, to_hit, fault=str(exc)), []

    async def _decide_with_llm(self, transfer: TransferEvent) -> tuple[Decision, list[RetrievedChunk]]:
        # 1. Gather cross-chain + sanctions context (network I/O concurrent-safe).
        from_profile = await self.debank.get_profile(transfer.from_address)
        to_profile = await self.debank.get_profile(transfer.to_address)
        from_hit = self.sanctions.lookup(transfer.from_address)
        to_hit = self.sanctions.lookup(transfer.to_address)

        # 2. Pull the most relevant HKMA / Cap 656 paragraphs from RAG.
        retrieved = self._retrieve_paragraphs(from_profile, to_profile, from_hit, to_hit)

        # 3. RiskAssessor characterizes the risk.
        risk_profile: RiskProfileOutput = self.risk_assessor.assess(
            transfer, from_profile, to_profile, from_hit, to_hit
        )
        logger.info(
            "Pipeline %s: risk_score=%d flags=%s",
            transfer.tx_hash[:10], risk_profile.score, risk_profile.flags,
        )

        # 4. ComplianceDecider picks the enforcement action and cites paragraphs.
        action_decision = self.decider.decide(transfer, risk_profile, retrieved)
        logger.info(
            "Pipeline %s: action=%s cited=%s",
            transfer.tx_hash[:10], action_decision.action, action_decision.paragraphs_cited,
        )

        # 5. Reporter writes the markdown XAI justification (Para 5.7).
        reasoning = self.reporter.report(transfer, risk_profile, action_decision, retrieved)

        normalized_paragraphs = [
            _normalize_paragraph_id(p) for p in action_decision.paragraphs_cited
        ]

        decision = Decision(
            transfer=transfer,
            action=Action(action_decision.action),
            target_address=action_decision.target_address,
            risk_score=action_decision.risk_score_final,
            paragraphs_cited=normalized_paragraphs,
            reasoning_md=reasoning,
        )
        return decision, retrieved

    def _fallback_decision(
        self,
        transfer: TransferEvent,
        from_hit,
        to_hit,
        *,
        fault: str = "",
    ) -> Decision:
        """Deterministic rule engine — bypasses LLM. Documents the fault inline."""
        fault_note = (
            f"[FALLBACK — LLM pipeline unavailable: {fault[:160]}]"
            if fault else "[FALLBACK — LLM pipeline unavailable]"
        )

        if to_hit is not None:
            return Decision(
                transfer=transfer,
                action=Action.FREEZE,
                target_address=transfer.to_address,
                risk_score=100,
                paragraphs_cited=[to_hit.paragraph_ref] if to_hit.paragraph_ref else ["7.5"],
                reasoning_md=(
                    f"{fault_note} Recipient {transfer.to_address} has a sanctions registry "
                    f"hit (tags={list(to_hit.tags)}, source={to_hit.source}). Per HKMA "
                    f"Para {to_hit.paragraph_ref or '7.5'}, an immediate FREEZE is mandatory. "
                    f"The licensee will hold the funds and escalate to JFIU under Chapter 8 "
                    f"once the agent's LLM pipeline is restored to draft the STR."
                ),
            )
        if from_hit is not None:
            return Decision(
                transfer=transfer,
                action=Action.FREEZE,
                target_address=transfer.from_address,
                risk_score=100,
                paragraphs_cited=[from_hit.paragraph_ref] if from_hit.paragraph_ref else ["7.5"],
                reasoning_md=(
                    f"{fault_note} Sender {transfer.from_address} has a sanctions registry "
                    f"hit (tags={list(from_hit.tags)}, source={from_hit.source}). "
                    f"FREEZE applied per Para {from_hit.paragraph_ref or '7.5'}."
                ),
            )
        return Decision(
            transfer=transfer,
            action=Action.PASS,
            target_address="",
            risk_score=0,
            paragraphs_cited=["5.4"],
            reasoning_md=(
                f"{fault_note} No sanctions match on either address. Conservative PASS "
                f"per Para 5.4 (risk-based ongoing monitoring); transfer will be re-evaluated "
                f"by the full LLM pipeline once restored."
            ),
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
