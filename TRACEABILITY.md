# Regulatory Traceability Matrix

Every load-bearing feature in this project traces to a specific paragraph or section in
either the **HKMA AML/CFT Guideline for Licensed Stablecoin Issuers (August 2025)** or
the **Stablecoins Ordinance (Cap. 656, consolidated 01-08-2025)**. This file is the
ground-truth of that mapping.

Two tiers:

- **Tier 1 — Decision-load-bearing**: paragraphs that directly shape an agent's prompt,
  a smart-contract function, or an audit-log field. A failure here would change the
  output of the system.
- **Tier 2 — RAG corpus only**: paragraphs that are ingested into Chroma and retrievable
  by the Risk Sentinel pipeline but not hard-wired into any single code path. They
  matter when the LLM cites them via RAG retrieval.

Total RAG corpus size: **408 chunks** (149 HKMA paragraph-level + 259 Cap 656 page-level).

---

## Tier 1 — HKMA AML/CFT Guideline (decision-load-bearing)

| Para | Topic | Feature | Implementation | Verification |
|---|---|---|---|---|
| **4.34** | Unhosted wallet definition; inherent ML/TF risk due to lack of regulatory oversight | RAG corpus background that anchors every decision | `_extracted/aml_guideline.txt:866` → ingest at `backend/rag/ingest.py::chunk_by_paragraph` | retrieved in every scenario's `retrieved_paragraphs` block; see dashboard /decisions |
| **4.39** | Screening unhosted wallet addresses at issuance / redemption for illicit-activity association | RiskAssessor anchors its system prompt on this duty; SanctionsRegistry lookup is the screening primitive | `backend/agent/risk_assessor.py::SYSTEM_PROMPT`; `backend/data/sanctions.py::SanctionsRegistry.lookup` | `sanctioned_recipient` scenario causes RAG to surface 4.39; ComplianceDecider cites it |
| **4.40** | Maintenance of customer wallet-address allow-list | RAG corpus, anchors ongoing monitoring narrative | RAG only (`_extracted/aml_guideline.txt`) | retrieved when query contains "monitoring" |
| **5.1, 5.4** | Risk-based ongoing monitoring scope and frequency | RiskAssessor risk scoring (0-100) calibrated to risk tiers per 5.4 | `backend/agent/risk_assessor.py::SYSTEM_PROMPT` (score anchors 0-19 / 20-49 / 50-79 / 80-100) | `clean_pass` scenario yields score < 20; `sanctioned_recipient` yields ≥ 80 |
| **5.7** | Written justification: "document the grounds for suspicion" | Reporter agent generates markdown XAI; persisted to `audit_records.reasoning_md` | `backend/agent/reporter.py::SYSTEM_PROMPT`; `backend/store/audit_log.py::AuditRecord.reasoning_md` | every audit row has a non-empty `reasoning_md`; dashboard "Agent reasoning" panel |
| **5.9–5.10** | Ongoing monitoring of stablecoins in circulation; on-chain freeze/burn capabilities | Listener subscribes to MockUSDC `Transfer` events on Arc; ExecutorAgent + MockUSDC supplies the on-chain primitives | `backend/chain/listener.py`; `contracts/src/MockUSDC.sol::{freezeAddress,refundTransfer,quarantineTransfer,burn}`; `backend/chain/executor.py` | `forge test` (18/18 PASS, role isolation incl. `test_SentinelCanFreeze`, `test_SentinelCannotBurn`); `backend/cli/m2_demo.py --unfreeze-first` end-to-end on Arc |
| **5.10(c)** | Freeze stablecoin promptly upon regulator / law-enforcement request | MockUSDC.freezeAddress invoked by sentinel-role address via Circle Wallets MPC | `contracts/src/MockUSDC.sol::freezeAddress` (SENTINEL_ROLE only); `backend/chain/executor.py::CircleWalletsSigner.freeze_address` | sample on-chain freeze tx on Arc Testnet `0xf39dce43c5...` (recorded in `docs/deployment.md`) |
| **5.11** | **MARQUEE.** "Effectiveness of unhosted wallet risk mitigating measures is yet to be proven — adopt cautious approach" | Project's raison d'être; ComplianceDecider system prompt anchors "cautious approach"; dashboard footer permanently quotes it | `backend/agent/compliance_decider.py::SYSTEM_PROMPT`; `dashboard/index.html::footer.marquee-citation` | dashboard footer renders the quote verbatim; ComplianceDecider's action policy biases toward caution on ambiguous high-risk |
| **5.12** | Promptly investigate + escalate suspicious wallet addresses via JFIU per Chapter 8 | Reporter mentions JFIU as the next operational step on FREEZE; ComplianceDecider cites 5.12 when sanctions hit | `backend/agent/reporter.py::SYSTEM_PROMPT` (point 4: "next operational step"); `backend/agent/compliance_decider.py` | scenario `sanctioned_recipient` → reasoning_md contains "Joint Financial Intelligence Unit" |
| **6.22–6.24** | Delay, intercept, or reverse suspicious transfers | MockUSDC.refundTransfer (force-return to sender) and quarantineTransfer (force-move to recovery wallet) | `contracts/src/MockUSDC.sol::refundTransfer`; `contracts/src/MockUSDC.sol::quarantineTransfer`; dispatched by `backend/chain/executor.py::Executor.execute` | `forge test::test_SentinelCanRefund`, `test_SentinelCanQuarantine` |
| **6.29** | Counterparty due diligence to avoid designated parties | SanctionsRegistry lookup + Manager's RAG query include sanctions-tag context | `backend/agent/manager.py::_retrieve_paragraphs` (signals include sanctions match tags) | `sanctioned_recipient` scenario surfaces 6.29 in retrieved + cited |
| **6.40–6.42** | P2P transfers to/from unhosted wallets between non-customer holders | CCTP inflow simulator injects cross-border tags so RAG retrieves these paragraphs; ComplianceDecider cites them on cross-chain scenarios | `backend/crosschain/cctp_simulator.py::build_cctp_inflow_context`; `backend/main.py` scenario `cctp_inflow_ethereum` | scenario `cctp_inflow_ethereum` retrieves 6.42; reasoning ties to cross-border designated party |
| **7.2–7.5** | Sanctions screening against UNSCR / HK gazette / HKMA notices | Static mock sanctions registry mirrors structure of OFAC SDN + HKMA gazette entries (production replaces with real upstream) | `backend/data/sanctions.py::SanctionsRegistry`; `backend/data/sanctions_mock.json` (paragraph_ref column tags each entry to a HKMA para) | sanctions hit pathway exercised by `sanctioned_recipient` scenario |
| **Ch 8** | Suspicious Transaction Reporting (STR) statutory obligation | Reporter writes the rationale that an MLRO would attach to an STR filing; mentions JFIU escalation | `backend/agent/reporter.py::SYSTEM_PROMPT` (Reporter is downstream content-producer for STR) | reasoning_md contains "Joint Financial Intelligence Unit" / "STR" |
| **Ch 9** | Record-keeping (statutory retention) | Append-only SQLite audit log; rows never updated, schema designed for long-term retention | `backend/store/audit_log.py::AuditLog`, `AuditRecord` model is `table=True` insert-only | `GET /decisions?limit=200` paginates indefinitely backwards; SQLite WAL preserves history |

## Tier 1 — Cap. 656 Stablecoins Ordinance

| Section | Topic | Feature | Implementation | Verification |
|---|---|---|---|---|
| **s.4** | Financial resources of a licensee | RAG corpus background (informational; not enforced at transaction level) | `_extracted/cap656.txt` ingested at page level | Cap 656 chunk `s4` retrievable via `python -m backend.rag.retrieve "licence financial resources"` |
| **s.15** | Application to the Monetary Authority for a licence | RAG corpus; cited only when LLM judges a question is about licensing rather than AML | `_extracted/cap656.txt` ingested at page level | Cap 656 chunk `s15` retrieved (top-1 for "licence application requirement"); see retrieve.py CLI smoke test |
| **s.171** | HKMA empowered to issue this AML/CFT Guideline | RAG corpus; provides the legal basis for everything in the HKMA Guideline | `_extracted/aml_guideline.txt:Para 1.1` references s.171 | retrieved alongside Guideline 1.1 |

---

## Tier 2 — RAG corpus only

The following HKMA paragraphs and Cap 656 sections are ingested and retrievable but do
not anchor any single hard-coded code path. They contribute when the LLM's RAG query
selects them as top-K. Documented here so an auditor knows what *could* be retrieved.

- **HKMA Guideline 1.x** — Introduction, scope, applicability
- **HKMA Guideline 2.x** — Risk assessment methodology
- **HKMA Guideline 3.x** — AML/CFT systems and policies
- **HKMA Guideline 4.x except 4.34/4.39/4.40** — CDD generally, e-KYC, simplified/enhanced DD
- **HKMA Guideline 5.2/5.3/5.5/5.6/5.8** — adjacent ongoing-monitoring detail
- **HKMA Guideline 6.1–6.21, 6.25–6.28, 6.30–6.39** — transfer mechanics, travel rule data fields, counterparty VASP DD
- **HKMA Guideline 7.6+** — sanctions screening operational detail beyond 7.2-7.5
- **Cap 656 s.1–s.3, s.5–s.14, s.16–s.159** — full ordinance body, page-chunked

---

## End-to-end verification commands

| Goal | Command |
|---|---|
| Confirm contract unit tests pass (18/18) | `cd contracts && forge test` |
| Confirm RAG ingestion produces 408 chunks | `python -m backend.rag.ingest` |
| Confirm RAG retrieval surfaces relevant paragraphs | `python -m backend.rag.retrieve "unhosted wallet sanctions screening"` |
| End-to-end Arc demo (Alice → Bob → freeze) | `python -m backend.cli.m2_demo --unfreeze-first` |
| Backend health + 3 demo scenarios | `uvicorn backend.main:app --port 8000`; then dashboard at `http://127.0.0.1:8000/dashboard/` |

## Self-audit checklist (pre-submission)

- [ ] `forge test` returns 18/18 PASS
- [ ] RAG ingestion succeeds with `Collection size: 408`
- [ ] All three scenarios produce non-empty audit rows
- [ ] Each FREEZE row has at least one cited paragraph that is present in its `retrieved_paragraphs`
- [ ] No cited paragraph contains a "Para " / "Section " prefix in audit data
- [ ] Sentinel wallet retains SENTINEL_ROLE on MockUSDC; cannot mint or burn
- [ ] Circle Wallets MPC successfully signs a freeze tx on Arc Testnet within 30s
