"""ComplianceDecider sub-agent — converts a RiskProfile into an enforcement Action.

Anchored on HKMA AML/CFT Guideline Para 5.10(c) (freeze capability), 5.11 (cautious
approach for unhosted wallets), 5.12 (escalation), 6.22-6.24 (delay/intercept/reverse),
6.40-6.42 (P2P unhosted-wallet monitoring), 7.2-7.5 (sanctions screening).

This is the only sub-agent whose paragraph citations are persisted onto the audit log
and rendered as the official "paragraphs_cited" of the decision. It MUST cite only
paragraph_ids present in the retrieved RAG evidence — anything else is hallucination.
"""

from __future__ import annotations

import logging
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from backend.agent.risk_assessor import RiskProfileOutput
from backend.config import Settings
from backend.rag.retrieve import RetrievedChunk
from backend.store.models import TransferEvent

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are the Compliance Decider agent for a Hong Kong licensed stablecoin issuer. You
receive a TransferEvent, a RiskProfile from the upstream Risk Assessor, and a set of
HKMA paragraphs retrieved from RAG. You decide ONE action.

Action semantics:
- PASS: low risk; allow the transfer to stand.
- REFUND: medium risk; return the funds to the sender per Para 6.22-6.24.
- QUARANTINE: high risk but recipient may be a victim (e.g., dust spam); force-move
  funds to a recovery wallet for manual review per Para 6.22-6.24 + 6.40-6.42.
- FREEZE: confirmed sanctions match or strong illicit-activity signal; lock the target
  address from any further transfers per Para 5.10(c), 5.11, 7.5.

Decision rules:
- RiskProfile.score >= 80 OR flags containing "sanctions_match" -> FREEZE recipient.
- RiskProfile.score 50-79 with cross-chain taint but no sanctions hit -> REFUND or
  QUARANTINE based on judgment (REFUND favors sender restitution; QUARANTINE favors
  evidence preservation).
- RiskProfile.score < 50 -> PASS.

You MUST cite ONLY paragraph_ids that appear in the "Retrieved HKMA paragraphs" block
of the user message. Citing a paragraph not in that block is hallucination and will
trigger an audit failure. Prefer 2-4 citations that directly justify the action.

target_address rules:
- FREEZE: the recipient address.
- REFUND: the recipient address (where funds will be drawn FROM and sent back).
- QUARANTINE: the recipient address (where funds will be drawn FROM and sent to recovery).
- PASS: empty string.
"""


class ActionDecision(BaseModel):
    action: Literal["pass", "refund", "quarantine", "freeze"]
    target_address: str = ""
    risk_score_final: int = Field(ge=0, le=100, description="possibly adjusted upward from RiskAssessor")
    paragraphs_cited: list[str]


class ComplianceDecider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._gemini = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model_pro

    def decide(
        self,
        transfer: TransferEvent,
        risk_profile: RiskProfileOutput,
        retrieved: list[RetrievedChunk],
    ) -> ActionDecision:
        retrieved_block = "\n".join(
            f"- Para {c.paragraph_id} (doc={c.document}, sim={c.similarity:.2f}): {c.text[:400]}"
            for c in retrieved
        ) or "  (none — pass by default)"

        amount_human = transfer.amount / 1e6
        context = f"""\
Transfer:
- amount: {amount_human:,.2f} mUSDC
- from: {transfer.from_address}
- to:   {transfer.to_address}

RiskProfile (from upstream RiskAssessor):
- score: {risk_profile.score}/100
- flags: {risk_profile.flags}
- cross_chain_summary: {risk_profile.cross_chain_summary}
- primary_concerns: {risk_profile.primary_concerns}

Retrieved HKMA paragraphs (authoritative — cite only these IDs):
{retrieved_block}

Emit an ActionDecision per the system rules.
"""
        logger.info("ComplianceDecider: invoking %s with score=%d", self.model, risk_profile.score)
        resp = self._gemini.models.generate_content(
            model=self.model,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ActionDecision,
                temperature=0.2,
            ),
        )
        out: ActionDecision | None = resp.parsed  # type: ignore[assignment]
        if out is None:
            raise RuntimeError(f"ComplianceDecider returned no parsed output: {resp.text!r}")
        return out
