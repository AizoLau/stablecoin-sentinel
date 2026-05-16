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
