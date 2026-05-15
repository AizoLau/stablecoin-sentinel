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
from backend.store.models import Action, Decision, TransferEvent

logger = logging.getLogger(__name__)


HKMA_PARAGRAPH_EXCERPTS = """\
HKMA AML/CFT Guideline for Licensed Stablecoin Issuers — paragraphs relevant to
unhosted-wallet P2P transfer monitoring:

- Para 4.39: When a customer uses an unhosted wallet (other than 4.37 exceptions) to
  receive stablecoins from a licensee at issuance or return stablecoins at redemption,
  the licensee should screen the wallet address to identify any transaction directly or
  indirectly associated with illicit/suspicious activities or designated parties.

- Para 5.4: A licensee should adopt a risk-based approach in ongoing monitoring; the
  scope and frequency of monitoring should be commensurate with the ML/TF risk.

- Para 5.7: A licensee should examine the background and purposes of transactions and
  document the grounds for any suspicion when transactions are inconsistent with the
  customer profile, unusually large/complex, or involve wallet addresses tied to
  illicit activities.

- Para 5.10(c): A licensee should have on-chain capabilities to freeze stablecoins
  promptly upon regulator / law-enforcement request or court order.

- Para 5.11 (MARQUEE): As the effectiveness of unhosted wallet risk mitigating
  measures is yet to be proven, the HKMA expects licensees to adopt a CAUTIOUS
  approach. Unless effectiveness can be demonstrated, identity of each holder should
  be verified.

- Para 5.12: If a licensee identifies stablecoin transactions or wallet addresses
  directly/indirectly associated with illicit activities or designated parties, it
  should promptly investigate and escalate via JFIU per Chapter 8.

- Para 6.22-6.24: A licensee should have the ability to delay, intercept, or reverse
  suspicious stablecoin transfers when warranted by AML/CFT risk.

- Para 6.40-6.42: P2P transfers to/from unhosted wallets between non-customer holders
  require ongoing monitoring per Para 5.9-5.12.

- Para 7.2-7.5: Sanctions screening against UNSCR / HK gazette / HKMA notices is
  mandatory; positive matches trigger immediate hold + investigation.
"""

SYSTEM_PROMPT = f"""\
You are the compliance decision agent for a Hong Kong licensed stablecoin issuer. You
monitor USDC P2P transfers between unhosted wallets on Arc Network and decide whether
to PASS, REFUND, QUARANTINE, or FREEZE based on AML/CFT risk.

{HKMA_PARAGRAPH_EXCERPTS}

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
    ):
        self.settings = settings
        self.debank = debank
        self.sanctions = sanctions
        self._gemini = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model_pro

    async def decide(self, transfer: TransferEvent) -> Decision:
        from_profile = await self.debank.get_profile(transfer.from_address)
        to_profile = await self.debank.get_profile(transfer.to_address)
        from_hit = self.sanctions.lookup(transfer.from_address)
        to_hit = self.sanctions.lookup(transfer.to_address)

        context = self._build_context(transfer, from_profile, to_profile, from_hit, to_hit)
        logger.info("Calling %s for transfer %s", self.model, transfer.tx_hash[:10])

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

    def _build_context(
        self,
        transfer: TransferEvent,
        from_profile: AddressProfile,
        to_profile: AddressProfile,
        from_hit: SanctionsHit | None,
        to_hit: SanctionsHit | None,
    ) -> str:
        amount_human = transfer.amount / 1e6  # mUSDC has 6 decimals
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

Decide the action per the system rules. Cite paragraphs precisely.
"""
