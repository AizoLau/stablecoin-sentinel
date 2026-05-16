"""Reporter sub-agent — produces the human-readable XAI justification.

Anchored on HKMA AML/CFT Guideline Para 5.7 (a licensee should document the grounds
for any suspicion when transactions are inconsistent with the customer profile,
unusually large/complex, or involve wallet addresses tied to illicit activities).

The Reporter does not make decisions. It writes the rationale that the auditor (or
the MLRO during STR drafting) will read. Output is markdown.
"""

from __future__ import annotations

import logging

from google import genai
from google.genai import types

from backend.agent.compliance_decider import ActionDecision
from backend.agent.risk_assessor import RiskProfileOutput
from backend.config import Settings
from backend.rag.retrieve import RetrievedChunk
from backend.store.models import TransferEvent

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are the Reporter agent. You receive a TransferEvent, the upstream RiskProfile, the
ComplianceDecider's ActionDecision, and the retrieved HKMA paragraphs that informed it.

Produce a concise markdown rationale (3-6 short sentences total) that satisfies HKMA
AML/CFT Guideline Para 5.7's requirement to "document the grounds for suspicion".

Required content:
1. State the action and the recipient/target.
2. Quote the specific evidence: sanctions tags, scam-tx counts, cross-chain signals.
3. Cite at least one of the paragraphs the ComplianceDecider chose, paraphrasing the
   relevant rule (do NOT introduce new paragraph_ids).
4. If action != PASS, mention the next operational step (e.g., "escalation to JFIU
   per Chapter 8" for sanctions hits).

Style:
- Plain prose with markdown formatting. No headings, no bullet lists unless natural.
- Do not restate the entire RiskProfile. Pick the load-bearing facts.
- Do not include "I" or "we"; write in the licensee's third-person voice
  ("the sentinel determined", "the licensee will hold the funds").
"""


class Reporter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._gemini = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model_pro

    def report(
        self,
        transfer: TransferEvent,
        risk_profile: RiskProfileOutput,
        decision: ActionDecision,
        retrieved: list[RetrievedChunk],
    ) -> str:
        cited = {c.paragraph_id: c for c in retrieved}
        cited_block = "\n".join(
            f"- Para {pid}: {cited[pid].text[:300]}..."
            for pid in decision.paragraphs_cited
            if pid in cited
        ) or "  (no retrieved citation available)"

        amount_human = transfer.amount / 1e6
        context = f"""\
Transfer: {amount_human:,.2f} mUSDC, {transfer.from_address} -> {transfer.to_address}.

RiskProfile:
- score: {risk_profile.score}/100
- flags: {risk_profile.flags}
- primary_concerns: {risk_profile.primary_concerns}
- cross_chain_summary: {risk_profile.cross_chain_summary}

ComplianceDecider action: {decision.action.upper()} on {decision.target_address!r}.
ComplianceDecider cited paragraphs: {decision.paragraphs_cited}

Paragraph excerpts available for paraphrasing:
{cited_block}

Write the markdown justification.
"""
        logger.info("Reporter: invoking %s", self.model)
        resp = self._gemini.models.generate_content(
            model=self.model,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
            ),
        )
        return (resp.text or "").strip()
