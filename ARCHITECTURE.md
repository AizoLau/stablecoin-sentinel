# Architecture

Detailed module structure, IO contracts, and data-flow walkthroughs for the
Unhosted Wallet Risk Sentinel. Reading order:

1. [High-level diagram](#high-level-diagram)
2. [Module IO contracts](#module-io-contracts)
3. [End-to-end data flow: `sanctioned_recipient` scenario](#data-flow-sanctioned_recipient)
4. [End-to-end data flow: `cctp_inflow_ethereum` scenario](#data-flow-cctp_inflow_ethereum)
5. [Design decisions and trade-offs](#design-decisions-and-trade-offs)
6. [Deployment topology](#deployment-topology)

---

## High-level diagram

```
                         ┌───────────────────────────────────────────────────────┐
                         │              Dashboard (vanilla HTML/JS)              │
                         │   live SSE feed | decision detail | RAG evidence pool │
                         └───────────────────────────▲───────────────────────────┘
                                                     │ EventSource (SSE)
   ┌─────────────────────────────────────────────────┴─────────────────────────────┐
   │                            FastAPI backend (backend/main.py)                  │
   │  GET /health     GET /decisions     GET /events (SSE)     POST /demo/trigger  │
   └────┬─────────────────────┬─────────────────────────────────┬──────────────────┘
        │                     │                                 │
        ▼                     ▼                                 ▼
   ┌──────────┐         ┌───────────┐                  ┌────────────────────┐
   │ Listener │         │ AuditLog  │                  │ ManagerAgent       │
   │ web3.py  │         │ SQLite    │                  │ (Python orchestrator)
   │ on Arc   │         │ (append)  │                  │                    │
   │ RPC      │         └───────────┘                  │ ┌────────────────┐ │
   └──────────┘                                        │ │ RiskAssessor   │ │  ─── gemini-flash ───┐
                                                       │ │  Para 4.39,5.4 │ │                      │
                                                       │ └───────┬────────┘ │                      │
                                                       │         │ RiskProfile                     │
                                                       │         ▼                                 │
                                                       │ ┌────────────────────┐                    │
                                                       │ │ ComplianceDecider  │ ── gemini-pro ─────┤
                                                       │ │  Para 5.10c, 5.11, │                    │
                                                       │ │  5.12, 6.40-42, 7.5│                    │
                                                       │ └───────┬────────────┘                    │
                                                       │         │ ActionDecision                  │
                                                       │         ▼                                 │
                                                       │ ┌────────────────────┐                    │
                                                       │ │     Reporter       │ ── gemini-pro ─────┘
                                                       │ │  Para 5.7 (XAI)    │
                                                       │ └───────┬────────────┘
                                                       │         │ reasoning_md
                                                       │         ▼
                                                       │ Decision (final)
                                                       └────┬───────────────────┘
                                                            │
                                                            ▼
                                                   ┌─────────────────┐         ┌──────────────────────┐
                                                   │ Executor        │ ──────► │ Circle Wallets API   │
                                                   │ (TxSigner)      │ MPC sig │ (Developer-Controlled)│
                                                   └────────┬────────┘         └──────────┬───────────┘
                                                            │                              │
                                                            │                              ▼
                                                            │                       ┌──────────────────┐
                                                            └─── audit row writes ─►│ MockUSDC on Arc  │
                                                                                    │ Testnet (5042002)│
                                                                                    └──────────────────┘

   ┌───────────────────────────────────────────────────────────────────────────────────────┐
   │  Shared services:                                                                     │
   │                                                                                       │
   │     ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐                       │
   │     │ DeBank      │    │ Sanctions    │    │ RAG (Chroma +    │                       │
   │     │ Cloud API   │    │ Registry     │    │ gemini-embedding-│                       │
   │     │ (85+ chains)│    │ (mock JSON)  │    │ 2, 3072-dim)     │                       │
   │     │             │    │              │    │ 408 chunks       │                       │
   │     │ AddressProf │    │ SanctionsHit │    │ HKMA + Cap 656   │                       │
   │     └─────────────┘    └──────────────┘    └──────────────────┘                       │
   └───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Module IO contracts

Every cross-module boundary is a Pydantic model — type-checked, JSON-serializable,
audit-loggable. Listed in pipeline order.

### `backend/store/models.TransferEvent`

```python
class TransferEvent(BaseModel):
    tx_hash: str          # 0x-prefixed Arc transaction hash
    block_number: int
    log_index: int
    from_address: str
    to_address: str
    amount: int           # raw units, 6 decimals (USDC convention)
    observed_at: datetime # UTC, listener wall-clock
```

Produced by `backend/chain/listener.py` (real chain events) or by
`backend/main.py::demo_trigger` (synthesized for the dashboard scenarios).

### `backend/data/debank_client.AddressProfile`

```python
@dataclass(frozen=True)
class AddressProfile:
    address: str
    total_usd_value: float
    chains_used: tuple[str, ...]
    chains_count: int
    tx_count_recent: int
    counterparty_addresses: tuple[str, ...]
    counterparty_count: int
    scam_tx_count: int                    # DeBank's is_scam flag
    scam_counterparties: tuple[str, ...]
    first_seen_ts: float | None
    last_seen_ts: float | None
```

Hits DeBank Cloud Pro at three endpoints
(`/v1/user/used_chain_list`, `/v1/user/total_balance`, `/v1/user/all_history_list`)
and aggregates locally. Retries up to 3× on transient errors via `tenacity`.

### `backend/data/sanctions.SanctionsHit`

```python
@dataclass(frozen=True)
class SanctionsHit:
    address: str
    tags: tuple[str, ...]      # e.g. ('known-mixer', 'sanctions-list')
    source: str                # e.g. 'DEMO-OFAC-001', 'DEMO-CCTP-INFLOW-ETHEREUM-MAINNET'
    added: str                 # ISO date
    paragraph_ref: str         # the HKMA para the tagging maps to (e.g. '7.5', '6.41')
```

In-memory hash-indexed lookup against `backend/data/sanctions_mock.json`. Demo
scenarios mutate this registry at runtime via `state.sanctions._index[addr] = ...`
without touching the persisted JSON.

### `backend/agent/risk_assessor.RiskProfileOutput`

```python
class RiskProfileOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    flags: list[str]                      # snake_case markers
    cross_chain_summary: str
    primary_concerns: list[str]
```

Gemini-flash JSON output, schema-enforced via `response_schema`. Score buckets
are documented in the system prompt and calibrated to HKMA Para 5.4 risk tiers.

### `backend/agent/compliance_decider.ActionDecision`

```python
class ActionDecision(BaseModel):
    action: Literal["pass", "refund", "quarantine", "freeze"]
    target_address: str = ""
    risk_score_final: int = Field(ge=0, le=100)
    paragraphs_cited: list[str]    # MUST appear in retrieved set
```

Gemini-pro JSON output. The system prompt enforces "cite only retrieved
paragraph_ids — anything else is hallucination". Manager subsequently strips any
`Para `/`Section ` prefix (`_normalize_paragraph_id`) so IDs match retrieved keys.

### `backend/store/models.Decision`

```python
class Decision(BaseModel):
    transfer: TransferEvent
    action: Action
    target_address: str
    risk_score: int
    paragraphs_cited: list[str]
    reasoning_md: str   # written by Reporter (gemini-pro)
```

Final assembled record. Persisted to `audit_records` table alongside the full
retrieved-chunks JSON for traceability.

### `backend/store/models.ExecutionReceipt`

```python
class ExecutionReceipt(BaseModel):
    tx_hash: str | None         # on-chain Arc tx hash if submitted
    status: str                 # "confirmed" | "failed" | "skipped"
    gas_used: int | None
    error: str | None
    submitted_at: datetime
```

---

## Data flow: `sanctioned_recipient`

```
1. POST /demo/trigger {scenario: "sanctioned_recipient", unfreeze_first: true}
   └─ FastAPI demo_trigger() runs

2. _unfreeze_target(Bob) on Arc
   └─ deployer-key OWNER calls MockUSDC.unfreezeAddress(Bob)
   └─ tx confirmed within 2-3 blocks

3. SanctionsRegistry._index[Bob.lower()] = SanctionsHit(
     tags=('known-mixer','sanctions-list'),
     source='DEMO-OFAC-001',
     paragraph_ref='7.5'
   )

4. Synthesize TransferEvent(from=Alice, to=Bob, amount=50e6, tx=0xaa..aa)

5. ManagerAgent.decide(transfer):
   a. await debank.get_profile(Alice)       → AddressProfile (likely empty for demo wallet)
   b. await debank.get_profile(Bob)         → AddressProfile (empty)
   c. sanctions.lookup(Bob)                 → SanctionsHit (the injected one)
   d. retriever.retrieve(query="unhosted wallet peer-to-peer transfer monitoring;
        sanctions screening positive match tags=['known-mixer','sanctions-list'];
        freeze stablecoin designated party")
        → top-8 chunks including 5.10, 6.29, 4.39, 5.4, 6.42, 6.39, 6.2, 5.8
   e. RiskAssessor.assess(...)              → score=95, flags=['sanctions_match','mixer_tag']
   f. ComplianceDecider.decide(...)         → action=FREEZE, target=Bob, paragraphs=['5.10','6.29','4.39']
   g. Reporter.report(...)                  → markdown with JFIU mention

6. Executor.execute(decision):
   └─ CircleWalletsSigner.freeze_address(Bob, "risk_score=95", "5.10, 6.29, 4.39")
   └─ POST /v1/w3s/developer/transactions/contractExecution to Circle API
      with freshly-encrypted entitySecretCiphertext (each OAEP encryption is unique)
   └─ Circle MPC-signs and submits to Arc
   └─ poll /v1/w3s/transactions/{id} until state == CONFIRMED
   └─ returns on-chain tx_hash 0xf39dce43c5...

7. AuditLog.append(transfer, decision, receipt, retrieved=[...8 chunks...])
   └─ row inserted, id auto-incremented

8. _broadcast({"type":"decision","record":{...}}) to all SSE subscribers
   └─ dashboard receives event, prepends to feed list, opens detail pane

9. Browser polls MockUSDC.frozen(Bob).call() via the dashboard's verification step
   └─ returns true ✓
```

End-to-end latency budget (measured on Arc Testnet):

| Step | Typical |
|---|---|
| RAG retrieval (1 Gemini embed + Chroma query) | 0.5–1.5 s |
| 3 Gemini LLM calls (Assessor + Decider + Reporter) | 8–14 s |
| Circle Wallets contractExecution + poll-to-confirmed | 6–12 s |
| Arc block inclusion | ~2 s |
| **Total** | **~20–25 s** |

---

## Data flow: `cctp_inflow_ethereum`

Identical to the sanctioned-recipient flow with three differences:

1. `cctp_simulator.build_cctp_inflow_context("ethereum", Bob, 50e6)` produces
   risk_tags `['cross-chain-cctp-inflow-from-ethereum',
   'tornado-cash-relay-history', 'cross-border-designated-party']`.
2. SanctionsHit injected with `paragraph_ref='6.41'`, `source='DEMO-CCTP-INFLOW-ETHEREUM-MAINNET'`.
3. Manager's `_retrieve_paragraphs` query incorporates the cross-chain tags →
   RAG returns Para 6.42 (P2P cross-border), 6.39 (shell VASP) in addition to
   the freeze cluster. ComplianceDecider tends to cite at least one
   cross-border paragraph.

The returned API payload includes a `cctp` field describing the simulated source
domain so the dashboard can display "🌉 from Ethereum mainnet (CCTP domain 0)".

---

## Design decisions and trade-offs

### Python orchestration over LLM-driven control flow

**Decision**: `ManagerAgent` is plain Python — it does not call an LLM. The four
agent roles (Assessor, Decider, Reporter, Executor) are wired together with
function calls, not ReAct-style tool loops.

**Why**:

- Determinism: control flow is auditable in source. An LLM-driven orchestrator
  can re-enter or skip steps non-deterministically.
- Cost: ReAct typically requires 3–10× LLM calls for the same outcome.
- Latency: each agent is one Gemini call. ReAct loops compound.
- Debuggability: errors surface at the exact sub-agent boundary.

**Cost of this choice**: less marketing surface for "fully autonomous agent
reasoning". We mitigate this by giving each sub-agent its own paragraph-anchored
system prompt and structured output — the autonomy is per-decision, not per-step.

### RAG over jamming the corpus into the system prompt

**Decision**: HKMA Guideline + Cap 656 (~408 chunks, 30-50 KB compressed) are
ingested to Chroma and retrieved per-decision. We do **not** keep the corpus in
every system prompt.

**Why**:

- Gemini has no prompt caching (unlike Claude). A 50 KB prompt × every call
  would cost 5–10× monthly.
- Retrieval gives the LLM only what's relevant, reducing
  context-stuffing-induced hallucination.
- Citations are verifiable: every `paragraphs_cited` entry can be checked
  against the retrieved-chunks JSON stored in the audit log.

### MockUSDC over real Circle USDC

**Decision**: We deploy our own ERC20 (`MockUSDC.sol`) on Arc Testnet rather
than using Circle's official USDC contract.

**Why**: Real USDC's `freeze` / `blacklist` privileges are issuer-only — we
cannot demonstrate `freeze` as a third-party developer. MockUSDC stands in for
the regulated asset and gives the sentinel role the issuer-tier capabilities the
HKMA Para 5.10(c) demands. In production, the same enforcement loop would be
invoked via Circle's official admin API.

The testnet USDC we hold (from `faucet.circle.com`) is used only as **gas** for
Arc transactions, not as the regulated asset.

### Circle Wallets MPC signing over local keystore

**Decision**: The sentinel's signing key lives in Circle's Developer-Controlled
Wallets MPC, not in the project's `.env`.

**Why**:

- Agent compromise alone cannot drain or inflate supply: the contract-level
  role isolation (sentinel ≠ owner) plus MPC-managed keys make an end-to-end
  attack require both LLM exploit *and* Circle account compromise.
- Real Circle integration — the most direct way to satisfy "uses Circle Wallets"
  on the submission checklist without paying lip service.

A `LocalKeystoreSigner` implementation of the same `TxSigner` protocol exists
for `forge anvil`-based local tests, but the production path is MPC.

### Page-chunked Cap 656

**Decision**: HKMA Guideline is chunked by paragraph identifier (1.1, 4.39,
5.10(c)). Cap 656 is chunked by PDF page.

**Why**: Cap 656's hierarchy nests 4 levels deep (Part → Division → Section →
sub-section (1)(a)(i)). Per-section chunks are too long (some sections span 4-6
pages of normative detail); per-sub-clause chunks are too short to retrieve
usefully. Per-page is a pragmatic middle ground that preserves semantic locality
+ uses the page footer (`Section N Cap. 656`) for a canonical metadata tag.

---

## Deployment topology

```
                                 ┌────────────────────────────┐
                                 │  Render / Railway          │
                                 │  (FastAPI + uvicorn worker)│
                                 │  https://<host>            │
                                 │     /dashboard/    /events │
                                 │     /decisions     /demo/* │
                                 └─────────────┬──────────────┘
                                               │
            ┌──────────────────────────────────┼──────────────────────────────────┐
            │                                  │                                  │
            ▼                                  ▼                                  ▼
   ┌─────────────────┐               ┌──────────────────┐               ┌───────────────────┐
   │ Arc Testnet RPC │               │ Circle Wallets   │               │ Gemini API        │
   │ (3 fallback)    │               │ Developer API    │               │ generativelanguage│
   │ - rpc.testnet   │               │ api.circle.com   │               │ .googleapis.com   │
   │   .arc.network  │               │                  │               │                   │
   │ - Alchemy       │               │                  │               │                   │
   │ - QuickNode     │               │                  │               │                   │
   └─────────────────┘               └──────────────────┘               └───────────────────┘
                                                                                  │
                                                                                  ▼
                                                                        ┌───────────────────┐
                                                                        │ Chroma (local SQLite)
                                                                        │ chroma_db/        │
                                                                        │ 408 vectors       │
                                                                        └───────────────────┘
   ┌─────────────────┐               ┌──────────────────┐
   │ DeBank Cloud Pro│               │ MockUSDC contract│
   │ pro-openapi     │               │ 0xA43143DF...    │
   │ .debank.com     │               │ on Arc Testnet   │
   └─────────────────┘               └──────────────────┘
```

For the hackathon demo, all services run from a single uvicorn process. The
RAG vector DB and the audit log are local SQLite files that ship with the
container image; cold-start ingestion is **not** required at runtime — the
`chroma_db/` directory is built once and committed-by-reference (via
`.gitignore` allowing the directory's existence but excluding contents) or
re-built post-deploy via a one-shot `python -m backend.rag.ingest` Render job.
