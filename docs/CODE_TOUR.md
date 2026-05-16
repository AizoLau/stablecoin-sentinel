# Code Tour — 30-minute onboarding for new contributors

You forked the repo. This guide gets you from "never seen this code" to "I could
add a new feature" in **about 30 minutes**: 10 minutes reading, 10 minutes running,
10 minutes mapping the extension points you care about.

If you only have 5 minutes, read [the elevator pitch](#elevator-pitch-60-seconds)
and skip to [the architecture in one sentence](#one-sentence-architecture).

---

## Elevator pitch (60 seconds)

This is a Hong Kong Stablecoin Challenge submission. It is an autonomous agent
that monitors USDC P2P transfers between unhosted wallets on **Circle Arc Testnet**,
evaluates them against the HKMA AML/CFT Guideline, and **executes on-chain
enforcement** (freeze / refund / quarantine) via the **Circle Wallets MPC API** —
end-to-end in under 25 seconds.

The whole project exists because the HKMA states in Para 5.11 that the
effectiveness of unhosted-wallet risk-mitigating measures is "yet to be proven".
This repo demonstrates one concrete answer: an agent loop that closes the gap
between *risk decision* and *on-chain enforcement* with full paragraph-level
traceability.

## One-sentence architecture

`Transfer event` → **(Risk Assessor → Compliance Decider → Reporter)** all
backed by **RAG retrieval over HKMA Guideline + Cap 656** → **Executor** signs
through **Circle Wallets MPC** → on-chain freeze on Arc.

---

## Reading order (10 minutes, no code execution)

Open these files in order. For each one I list the *single question* it answers,
so you can skim faster than you would left-to-right.

1. **[`README.md`](../README.md)** — *"What is this project and what does success look like?"*
   - Read: the elevator pitch + the "Demo at a glance" table + the architecture diagram.
   - Skim the rest.

2. **[`docs/demo_script.md`](./demo_script.md)** — *"What does the dashboard show, step by step?"*
   - Read the three scenario sections (1:00 – 2:55).
   - This is more concrete than `README.md` because it walks the dashboard.

3. **[`ARCHITECTURE.md`](../ARCHITECTURE.md)** — *"What are the moving pieces and why are they separate?"*
   - Read the high-level diagram + "Module IO contracts" + "Design decisions and trade-offs".
   - Skip "Deployment topology" unless you're deploying.

4. **[`TRACEABILITY.md`](../TRACEABILITY.md)** — *"Where in the code does HKMA Para X live?"*
   - Use as a reverse-index when you have a specific regulation in mind.
   - Do not read top-to-bottom; jump to whatever paragraph you care about.

By now you should be able to answer: *"If sanctions registry hits the recipient,
what happens?"* If yes, move on. If no, re-read `ARCHITECTURE.md`'s data-flow
section.

For **lookup-style reference docs** (which you don't read top-to-bottom, you
search through):

- **[`docs/API.md`](./API.md)** — every REST endpoint's request/response schema + curl examples
- **[`docs/CONTRACTS.md`](./CONTRACTS.md)** — MockUSDC function/event/error/role reference + gas costs
- **[`docs/PROMPTS.md`](./PROMPTS.md)** — verbatim agent system prompts + design rationale + tuning guidance
- **[`docs/ENV.md`](./ENV.md)** — environment variable dictionary (purpose / required / example / source)

---

## Run it (10 minutes)

You need three API keys: **Gemini** (`aistudio.google.com/apikey`),
**DeBank Cloud** (`cloud.debank.com`), and **Circle Developer-Controlled
Wallets** (`console.circle.com`). The Circle one is the most friction — see
[`docs/circle_product_feedback.md`](./circle_product_feedback.md) for the
gotchas we hit.

You also need:

- The MockUSDC contract deployed on Arc Testnet (the deployer wallet's private
  key + the contract address)
- A sentinel Circle Wallet on Arc Testnet with `SENTINEL_ROLE` granted on the
  MockUSDC

The repo ships with **our** deployed addresses in `docs/deployment.md` and
`.env.example` — if you're a forker who only wants to *understand* the code,
you don't need to redeploy. Skip to step 3 below and just point your `.env`
at our MockUSDC; your `freeze` calls will fail (you don't have SENTINEL_ROLE)
but the agent pipeline up to the executor will work.

```powershell
# 1. Clone with submodules (OpenZeppelin + forge-std are pinned via .gitmodules)
git clone --recursive https://github.com/AizoLau/stablecoin-sentinel.git
cd stablecoin-sentinel

# 2. Install Python deps
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .

# 3. Fill in .env (copy from .env.example, paste the three API keys)
copy .env.example .env
notepad .env

# 4. Smoke-test the RAG retriever (no chain calls, no LLM calls except the embed)
.\.venv\Scripts\python.exe -m backend.rag.retrieve "unhosted wallet sanctions screening"
# Expect: top-8 paragraphs including 4.39, 5.10, 6.29 etc.

# 5. Run the full pipeline end-to-end (this DOES make on-chain calls)
.\.venv\Scripts\python.exe -m backend.cli.m2_demo --unfreeze-first

# 6. Start the backend + dashboard
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000
# Browser: http://127.0.0.1:8000/dashboard/
```

If you got a freeze tx hash back from step 5, you're operational.

---

## Code tour (10 minutes)

The repo is laid out so each layer corresponds to one logical responsibility.
Read in this order; the question each file answers is in italics.

### Layer 1 — IO contracts (read first; everything else references these)

| File | Why read it |
|---|---|
| **[`backend/store/models.py`](../backend/store/models.py)** | *What types flow between modules?* Pydantic models for `TransferEvent`, `RiskProfile`, `Decision`, `ExecutionReceipt`. Every other module produces or consumes one of these. |
| **[`backend/config.py`](../backend/config.py)** | *What environment variables exist?* The `Settings` class is the single source of truth. |

### Layer 2 — Data sources (the "what does the agent know")

| File | Why read it |
|---|---|
| **[`backend/data/debank_client.py`](../backend/data/debank_client.py)** | *How does the agent see a wallet's cross-chain history?* DeBank Pro API wrapper. Returns `AddressProfile`. |
| **[`backend/data/sanctions.py`](../backend/data/sanctions.py)** + **[`sanctions_mock.json`](../backend/data/sanctions_mock.json)** | *What's "sanctioned" mean in this system?* Local hash-indexed registry mirroring OFAC SDN / HKMA gazette schema. Production hot-swappable. |
| **[`backend/rag/ingest.py`](../backend/rag/ingest.py)** | *How are HKMA + Cap 656 chunked and embedded?* HKMA by paragraph, Cap 656 by page. |
| **[`backend/rag/retrieve.py`](../backend/rag/retrieve.py)** | *How does the agent fetch relevant law per decision?* Chroma vector search wrapping Gemini embeddings. |

### Layer 3 — Agents (the "what the agent thinks")

| File | Why read it |
|---|---|
| **[`backend/agent/manager.py`](../backend/agent/manager.py)** | *How are the four agents wired?* Plain Python orchestration — no LLM. Read this first; it's the spine. |
| **[`backend/agent/risk_assessor.py`](../backend/agent/risk_assessor.py)** | *How is a wallet risk-scored?* Single Gemini-flash call. System prompt anchored on Para 4.39, 5.4. |
| **[`backend/agent/compliance_decider.py`](../backend/agent/compliance_decider.py)** | *How is the enforcement action chosen?* Single Gemini-pro call. Must cite only retrieved paragraph_ids. |
| **[`backend/agent/reporter.py`](../backend/agent/reporter.py)** | *Who writes the human-readable rationale?* Single Gemini-pro call. Para 5.7 (written justification). |

### Layer 4 — On-chain execution (the "what the agent does")

| File | Why read it |
|---|---|
| **[`contracts/src/MockUSDC.sol`](../contracts/src/MockUSDC.sol)** | *What can the agent actually do on-chain?* ERC20 + AccessControl. Sentinel role is restricted: freeze/refund/quarantine only — cannot mint or burn. |
| **[`contracts/test/MockUSDC.t.sol`](../contracts/test/MockUSDC.t.sol)** | *What invariants must hold?* 18 Foundry tests including role isolation. Run with `cd contracts && forge test`. |
| **[`backend/chain/circle_wallets.py`](../backend/chain/circle_wallets.py)** | *How does the agent's signing happen?* Circle Developer-Controlled Wallets API client. Each request encrypts the entity secret fresh (anti-replay). |
| **[`backend/chain/executor.py`](../backend/chain/executor.py)** | *How does a `Decision` become a transaction?* `TxSigner` protocol + `CircleWalletsSigner` implementation. |
| **[`backend/chain/listener.py`](../backend/chain/listener.py)** | *How does the agent observe the chain?* web3.py Transfer event subscription on Arc. Not invoked in M5 demo path (the dashboard uses `/demo/trigger` instead), but used in production. |

### Layer 5 — API + UI

| File | Why read it |
|---|---|
| **[`backend/main.py`](../backend/main.py)** | *What endpoints are exposed?* FastAPI: `/health`, `/decisions`, `/events` (SSE), `/demo/trigger`. |
| **[`backend/store/audit_log.py`](../backend/store/audit_log.py)** | *Where do decisions get persisted?* SQLite append-only. |
| **[`dashboard/app.js`](../dashboard/app.js)** | *How does the UI subscribe + render?* Vanilla JS, EventSource for SSE. No build step. |
| **[`backend/crosschain/cctp_simulator.py`](../backend/crosschain/cctp_simulator.py)** | *How is CCTP inflow simulated without invoking real USDC?* Tag-based context injection. |

---

## Extension points (10 minutes — what would you change?)

These are the seams you'd most likely touch when extending the project.

### Add a new demo scenario (e.g. travel-rule data missing)

1. Add a new `scenario` literal in `backend/main.py::DemoTriggerBody`.
2. In `demo_trigger()`'s scenario `if/elif` chain, inject your tag set into
   `state.sanctions._index[to_addr.lower()]` (or skip injection for clean cases).
3. Add a corresponding button to `dashboard/index.html` with
   `data-scenario="your_scenario_name"`.

No code in the agent layer needs to change — the agent reads sanctions tags
generically and the RAG retriever picks paragraphs by query similarity.

### Swap Gemini for another LLM (Claude / OpenAI / local)

The three sub-agents (`risk_assessor.py`, `compliance_decider.py`,
`reporter.py`) each have a `_gemini` field constructed in `__init__`. Swap that
for the new SDK and adapt the response-parsing in `assess()` / `decide()` /
`report()`. The Pydantic output schemas don't need to change. Note that you'd
also swap `backend/rag/ingest.py::EMBED_MODEL` and `retrieve.py::EMBED_MODEL`
to the new provider's embedding model.

### Add a new sanctions source (real OFAC SDN, Chainalysis)

`backend/data/sanctions.py::SanctionsRegistry` is the single integration point.
Replace `_load()` with HTTP fetch + a periodic refresh task. Keep the
`SanctionsHit` dataclass shape so downstream agents don't change.

### Move from Arc to another EVM chain

Update `ARC_RPC_URL`, `ARC_CHAIN_ID`, `ARC_EXPLORER_URL` in `.env`. Verify that
your destination chain is in Circle Wallets'
[supported blockchains list](https://developers.circle.com/wallets/dev-controlled/create-your-first-wallet)
(`ARC-TESTNET` is — `ETH-SEPOLIA`, `BASE-SEPOLIA`, `ARB-SEPOLIA`, etc. are
alternatives). Redeploy MockUSDC there. Grant `SENTINEL_ROLE` to the Circle
sentinel wallet on the new chain.

### Replace MockUSDC with the real USDC contract

You'd lose the ability to call `freezeAddress` as a third party — only Circle
as the USDC issuer can do that on the real contract. The way to integrate with
real USDC is to **submit a freeze request to Circle's compliance API**
(not on-chain, off-chain). The architecture supports this: replace
`CircleWalletsSigner` with a new `CircleComplianceAPISigner` implementing the
same `TxSigner` protocol. The agent pipeline upstream stays the same.

### Production-ize the RAG corpus

Currently `_extracted/aml_guideline.txt` and `_extracted/cap656.txt` are static
text we extracted from the HKMA PDFs once. For production:

1. Subscribe to the HKMA + Cap 656 update RSS/email (or scrape `legco.gov.hk`).
2. On new version, re-run `python -m backend.rag.ingest`. Chroma `upsert` is
   idempotent on `chunk_id`, so unchanged paragraphs stay in place.
3. Audit log preserves the `retrieved_paragraphs` text per decision, so you can
   prove what version of the corpus the agent saw on any given date.

---

## Things to verify before contributing

- `forge test` returns **18/18 PASS** (run from `contracts/`).
- `python -m backend.rag.ingest` succeeds with **`Collection size: 408`**.
- `python -m backend.cli.m2_demo --unfreeze-first` produces an on-chain freeze tx
  visible on the Arc explorer link in its output.

If all three pass, your environment is good.

---

## Open questions / known limitations

- **Reporter's paragraph citations are LLM-chosen**, not strictly retrieved-ranked.
  The agent must cite *only* retrieved paragraph IDs (enforced by system prompt and
  audited by `manager._normalize_paragraph_id`), but it does not have to cite the
  top-1 by similarity. This is intentional: highest similarity ≠ most regulatorily
  relevant, and we trust gemini-pro's domain reasoning.
- **The listener is implemented but not invoked in the M5 demo path.** The
  dashboard uses `/demo/trigger` to synthesize transfers. Production would wire
  `listener.py` directly into a Manager queue. This is M3-B "future work" that
  ends up actually being trivial to plug in.
- **No real CCTP burn-mint on testnet.** The CCTP simulator is purely
  software-level. To do real CCTP burn-and-mint you'd need a `CCTPReceiver`
  contract on Arc that wraps Circle's `MessageTransmitter` — a clean extension
  but not necessary for the regulatory-traceability story.
- **Free-tier deployments sleep.** Render free tier sleeps after 15 min idle.
  Pre-warm before recording. See `docs/deploy.md`.

---

## Where to ask questions

Open a GitHub Issue on https://github.com/AizoLau/stablecoin-sentinel. Specifically
useful labels: `architecture`, `extension`, `regulation` (for HKMA / Cap 656
interpretation questions).
