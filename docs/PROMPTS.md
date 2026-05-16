# Agent Prompts — verbatim + design rationale

The three sub-agents are the only LLM-driven components in the system. Their
behavior is entirely defined by their system prompts plus a strict Pydantic
output schema. This document is the reference for *why* each prompt is written
the way it is and how to tune it.

If you change a prompt, change it here too — this file is the contract.

| Sub-agent | Model | File | Output schema |
|---|---|---|---|
| Risk Assessor | `gemini-2.5-flash` | `backend/agent/risk_assessor.py` | `RiskProfileOutput` |
| Compliance Decider | `gemini-2.5-pro` | `backend/agent/compliance_decider.py` | `ActionDecision` |
| Reporter | `gemini-2.5-pro` | `backend/agent/reporter.py` | (plain markdown string) |

All three are called with `temperature=0.2` (Risk + Decider) or `temperature=0.3`
(Reporter) to bias toward consistency while preserving enough variation that
two consecutive runs aren't byte-identical (good for video demo retakes).

---

## 1. Risk Assessor

**Role**: characterize the wallet risk. Does **not** decide an action.

**Why a separate sub-agent**: separating risk *characterization* from risk
*response* lets the system swap the response policy (FREEZE / QUARANTINE /
PASS thresholds) without retraining the assessor. It also means the assessor's
output is reusable for non-enforcement downstream tasks (analytics, dashboards).

### Verbatim system prompt

```text
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
```

### Design notes

- **Score-bucket anchors**: explicit numeric tiers prevent the LLM from drifting
  into "I'll just say 50 for everything ambiguous". The four anchors mirror
  HKMA Para 5.4 risk tiers (low / medium / high / severe).
- **`flags` is a free-form `list[str]`** rather than a fixed `Literal[]`. We
  considered enforcing an enum, but Gemini's structured-output support for
  arrays of enums is shakier than for arrays of strings, and downstream the
  Compliance Decider treats flags as soft signals anyway.
- **"Do NOT prescribe an action"**: trial runs without this line frequently
  saw the assessor write "and the transfer should be frozen" in
  `cross_chain_summary`. Explicit prohibition fixes it.
- **No retrieved paragraphs**: the assessor doesn't get RAG context. Risk
  characterization is contextual to the *wallet*, not to the *regulation*.
  The Compliance Decider is the only sub-agent that gets RAG paragraphs.

### Tuning guidance

| If you want to … | Change |
|---|---|
| Make the assessor more cautious (higher scores) | Shift the anchors: "20-39: mild …, 40-69: moderate …, 70-100: severe …". |
| Encourage less-common flags (e.g. mixer, dust spam) | Add concrete example flags to the prompt's parenthetical list. |
| Speed up (cheaper) | Already on Gemini Flash. No further speedup short of switching to a local small model. |
| Reduce false positives on fresh wallets | Tighten the 20-49 anchor: "20-49: mild signal — fresh wallet alone is not enough; must combine with at least one other adverse signal". |

---

## 2. Compliance Decider

**Role**: pick exactly one enforcement action (PASS / REFUND / QUARANTINE / FREEZE)
and cite the HKMA paragraphs justifying it.

**Why a separate sub-agent**: this is the only sub-agent whose paragraph
citations are persisted as the official `paragraphs_cited` of the audit row.
Concentrating that responsibility in one prompt lets us enforce the strictest
"cite only retrieved IDs" rule there, and leave the other two sub-agents free
to talk regulation in informal prose.

### Verbatim system prompt

```text
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
```

### Design notes

- **Action semantics with paragraph anchors**: each action's documentation
  cites the HKMA paragraph that authorizes it. This is doctrine smuggling —
  the LLM learns the regulatory mapping by reading the system prompt, then
  reuses it when deciding which paragraph to cite.
- **Decision rules as score thresholds**: explicit if/then bands prevent the
  LLM from inventing new ones. The 80/50 cliffs are conservative — they mean
  any clear sanctions hit goes FREEZE without ambiguity, and PASS requires
  genuine cleanness.
- **The "cite ONLY retrieved IDs" rule**: this is the project's
  hallucination-defense backbone. The Manager normalizes citations
  (`_normalize_paragraph_id`) and the audit log persists the retrieved set so
  any out-of-set citation is visible in the dashboard as
  "⚠ possible hallucination".
- **`target_address` rules**: prevents the common mistake of "FREEZE Alice"
  when Bob is the bad actor. The rules tie each action to the natural target.
- **2-4 citations**: empirically, fewer is undertyped (hard to audit), more
  is noise. The Reporter downstream paraphrases at most 2.

### Tuning guidance

| If you want to … | Change |
|---|---|
| Make the agent more permissive | Raise FREEZE threshold ("score >= 90"), lower PASS ceiling ("score < 30"). |
| Encourage REFUND over QUARANTINE | Strengthen "REFUND favors sender restitution" line; add example. |
| Add a new action (e.g. ESCALATE_ONLY for log without acting) | Add it to "Action semantics" + "Decision rules" + the `Literal[]` in `ActionDecision`. Also extend `backend/store/models.Action` enum + `chain/executor.py::Executor.execute`. |
| Force a specific citation pattern (e.g. always cite 5.11 on FREEZE) | Append "FREEZE actions MUST cite Para 5.11" to the rules. Beware: if 5.11 isn't in the retrieved set for that decision, the agent will fail to comply. Better to ensure it's retrieved by tweaking the Manager's RAG query. |

### Anti-pattern to avoid

Do **not** dump the full retrieved chunks into the system prompt. The system
prompt is constant across calls; the retrieved chunks are per-call. Mixing them
breaks Gemini's response caching (already absent for Gemini, but you'd block
any future optimization) and bloats the prompt unnecessarily.

---

## 3. Reporter

**Role**: write the human-readable markdown justification (HKMA Para 5.7).

**Why a separate sub-agent**: the Compliance Decider's output is structured
JSON — perfect for the audit log and downstream automation, but not what an
MLRO wants to read when drafting an STR. The Reporter translates JSON into
prose, with explicit operational next-steps.

### Verbatim system prompt

```text
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
```

### Design notes

- **3-6 sentences**: forces compression. Without this, Gemini-pro writes
  paragraph after paragraph and the dashboard panel scrolls.
- **Four numbered required-content points**: each one maps to an audit
  expectation. (1) is "what action did you take", (2) is "what evidence",
  (3) is "what regulation", (4) is "what's next". Removing any of these
  produced auditor-flagged rationales in our spot-check.
- **"Do NOT introduce new paragraph_ids"**: the Reporter is downstream of the
  Decider's citations. If the Reporter invented its own citation, audit
  consistency would break — `paragraphs_cited` is what's persisted, the
  Reporter just paraphrases. Tested by trying "say something about Para 5.11
  even if not cited" — the system prompt suppresses this.
- **Third-person voice**: "the sentinel determined" reads like an audit log
  entry, not a chatbot response. Critical for compliance optics.

### Tuning guidance

| If you want to … | Change |
|---|---|
| Longer rationales (more detail) | Increase the sentence cap: "5-10 short sentences". |
| Multilingual output (English + Chinese for HKMA bilingual audit) | Add to the style block: "After the English rationale, append the same content in Traditional Chinese under a `### 中文` header." |
| Insert a structured FOR / AGAINST analysis | Replace "no bullet lists" with a forced template: "Format the body as ### Evidence (bullets) / ### Counter-considerations (bullets) / ### Conclusion (one sentence)." |
| Generate STR-ready output | Add a final sentence requirement: "End with a one-line declaration suitable for direct inclusion in an STR submitted to JFIU." |

---

## Cross-cutting concerns

### Hallucination defense (paragraph citations)

Three layers:

1. **System prompt enforcement**: Compliance Decider is told "cite ONLY retrieved
   IDs".
2. **Manager-side normalization**: `_normalize_paragraph_id` strips prefixes
   like "Para " / "Section " so `"Para 5.10"` and `"5.10"` are treated
   identically.
3. **Audit persistence + dashboard rendering**: `retrieved_paragraphs` is
   stored alongside `paragraphs_cited`; the dashboard renders any cited ID not
   in the retrieved set with a red "⚠ possible hallucination" badge.

In production, layer 4 would be a hard rejection — refuse to persist the
audit row + return 422 to the dashboard. We log+warn for now so the demo can
still show what hallucination looks like.

### Temperature

| Agent | Temperature | Why |
|---|---|---|
| Risk Assessor | 0.2 | Numeric scoring should be near-deterministic for the same evidence. |
| Compliance Decider | 0.2 | Action selection is rule-bounded; low temperature reduces noise. |
| Reporter | 0.3 | Slight variation in phrasing helps avoid repetitive-looking audit rows when scenarios are similar. |

### Why three separate calls instead of one big prompt

Tradeoff:

- **Pro of separation**: each prompt is shorter (Gemini handles short prompts
  more reliably + the response is more focused). Failures localize: a
  Reporter regression doesn't impact action selection.
- **Con of separation**: 3× the latency vs. one call. We accept this: total
  ~13s of LLM time is dominated by the network round-trip to Gemini regardless
  of prompt size, and serial > parallel here because each stage depends on the
  prior stage's output.

### Why not function-calling / ReAct

Gemini's function-calling is reliable but adds complexity (the model decides
which function to call, when, with what args). For a 3-stage linear pipeline
with rigid contracts, Python orchestration is simpler to debug and reason
about. See `ARCHITECTURE.md::Design decisions` for the long version.

### Adding a fourth sub-agent

The pattern to follow:

1. Create `backend/agent/<your_agent>.py` with a Pydantic output model and
   a class with a single method that takes structured inputs and returns the
   model.
2. Inject it in `backend/agent/manager.py::ManagerAgent.__init__`.
3. Call it in the appropriate place in `decide()`.
4. If its output should be persisted to the audit log, extend
   `backend/store/audit_log.py::AuditRecord` with the new field.
5. Add a section to this file documenting the new prompt.
