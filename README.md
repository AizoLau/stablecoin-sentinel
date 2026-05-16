# Unhosted Wallet Risk Sentinel

> An autonomous AML/CFT agent that monitors USDC peer-to-peer transfers between
> unhosted wallets on **Arc Testnet**, evaluates them against the HKMA AML/CFT
> Guideline for Licensed Stablecoin Issuers, and **executes on-chain enforcement**
> (freeze / refund / quarantine) via **Circle Wallets** MPC signing — all in under
> 25 seconds end-to-end.

Submission for the **Hong Kong Stablecoin Challenge — Track 4: Agentic Economy**
(hosted by Ignyte, sponsored by Circle + Arc).

> **New to this repo?** Start with [`docs/CODE_TOUR.md`](./docs/CODE_TOUR.md) —
> a 30-minute onboarding guide with reading order, run commands, and extension
> points. For reference docs (lookup, not narrative):
> [`API.md`](./docs/API.md) /
> [`CONTRACTS.md`](./docs/CONTRACTS.md) /
> [`PROMPTS.md`](./docs/PROMPTS.md) /
> [`ENV.md`](./docs/ENV.md). For architecture / regulatory mapping:
> [`ARCHITECTURE.md`](./ARCHITECTURE.md) / [`TRACEABILITY.md`](./TRACEABILITY.md).
> For deployment + submission: [`deploy.md`](./docs/deploy.md) /
> [`SUBMISSION.md`](./docs/SUBMISSION.md) / [`demo_script.md`](./docs/demo_script.md).

---

## Why this project exists

The HKMA's August 2025 AML/CFT Guideline for Licensed Stablecoin Issuers gives the
industry a unique regulator-acknowledged gap:

> *"As the effectiveness of these risk mitigating measures is yet to be proven, the
> HKMA expects licensees to adopt a cautious approach in determining whether their
> systems are adequate for mitigating ML/TF risks associated with licensed stablecoin
> activities, in particular as regards peer-to-peer transfers between unhosted wallets."*
> — **HKMA AML/CFT Guideline Para 5.11**

Today's stack offers either *risk scoring* (Chainalysis, TRM) or *user-experience
wallets* (MetaMask). Nothing closes the loop between **risk decision** and **on-chain
enforcement** for unhosted-wallet activity. That gap is what this project fills.

---

## Demo at a glance

The Risk Sentinel runs three demonstration scenarios out of the box:

| Scenario | What happens | HKMA paragraphs typically cited |
|---|---|---|
| 🔒 **Sanctioned recipient** | Recipient address is on the mock sanctions registry. Agent freezes the address on-chain via Circle Wallets MPC. | 5.10(c), 5.11, 5.12, 7.5 |
| 🌉 **CCTP inflow from Ethereum** | Simulated cross-chain USDC inflow from a Tornado-Cash-tagged source. Agent freezes + cites cross-border rules. | 6.40–6.42, 5.11, 7.5 |
| ✅ **Clean transfer** | Both addresses pass screening. Agent issues `PASS` action with a low risk score. | 4.39, 5.4 (negative case) |

Every decision is paragraph-anchored: each citation must come from a chunk that
the **RAG retriever** actually returned for that decision — no hallucinations
allowed. The dashboard surfaces both the agent's chosen citations and the full
top-K retrieved evidence pool side by side so an auditor can verify the agent did
not paraphrase a rule it never read.

---

## Quick start

### Prerequisites

- **Python 3.11+** (we ship a `venv` against Miniconda's Python 3.13.11)
- **Foundry** (`forge` 1.5+) — install from https://book.getfoundry.sh/
- **Node.js** is not required (dashboard is vanilla HTML/JS)
- Three API keys: **Gemini** (https://aistudio.google.com/apikey), **DeBank Cloud**
  (https://cloud.debank.com), **Circle Developer Account**
  (https://console.circle.com/signup → Developer-Controlled Wallets)

### Setup

```powershell
# 1. Clone with submodules + install Python deps
git clone --recursive <this-repo>
cd stablecoin-sentinel
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .

# If you forgot --recursive on clone, initialize submodules now
# (OpenZeppelin v5.6.1 + forge-std v1.16.1 are pinned via .gitmodules)
git submodule update --init --recursive

# 3. Fill in .env (use .env.example as template)
# Required:
#   GEMINI_API_KEY=
#   DEBANK_ACCESSKEY=
#   CIRCLE_API_KEY=        (from Circle Console)
#   CIRCLE_ENTITY_SECRET=  (32-byte hex, registered with Circle)
#   CIRCLE_SENTINEL_WALLET_ID=     (created via Circle API; see scripts/)
#   CIRCLE_SENTINEL_WALLET_ADDRESS=

# 4. Deploy MockUSDC to Arc Testnet
#    Fund deployer + sentinel wallets via https://faucet.circle.com (Arc Testnet)
cd contracts
set -a; source ../.env; set +a
forge script script/Deploy.s.sol:Deploy --rpc-url https://rpc.testnet.arc.network --broadcast
cd ..

# 5. Grant SENTINEL_ROLE to the Circle Wallet
#    (one cast send; see docs/deployment.md for the exact command)

# 6. Ingest the regulatory corpus into Chroma
.\.venv\Scripts\python.exe -m backend.rag.ingest

# 7. Start the backend + dashboard
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000

# Dashboard: http://127.0.0.1:8000/dashboard/
```

### Verify

```powershell
# Unit tests (contracts)
cd contracts && forge test      # 18/18 PASS

# RAG smoke test
python -m backend.rag.retrieve "unhosted wallet sanctions screening"

# End-to-end CLI demo (reproducible)
python -m backend.cli.m2_demo --unfreeze-first
```

---

## Architecture

```
   ┌─────────────────────────────────────────────────────────────────┐
   │                Dashboard (vanilla HTML/JS, SSE)                 │
   └────────────────────────────────▲────────────────────────────────┘
                                    │ SSE
   ┌────────────────────────────────┴────────────────────────────────┐
   │  FastAPI backend:  /health  /decisions  /events  /demo/trigger  │
   └────┬───────────────┬───────────────┬──────────────────┬─────────┘
        │               │               │                  │
        ▼               ▼               ▼                  ▼
   ┌────────┐    ┌──────────┐    ┌────────────┐     ┌─────────────┐
   │Listener│    │ SQLite   │    │  Manager   │     │ CCTP        │
   │(web3.py│    │audit_log │    │(orchestrator)    │ Simulator   │
   │ on Arc)│    └──────────┘    └──┬─────────┘     └─────────────┘
   └────────┘                       │
                                    ├── RiskAssessor  (gemini-flash)  [Para 4.39, 5.4]
                                    ├── ComplianceDecider (gemini-pro)[Para 5.10c, 5.11, 7.5]
                                    ├── Reporter      (gemini-pro)    [Para 5.7]
                                    └── Executor → Circle Wallets API ──> Arc Testnet
                                                                          (MockUSDC)
                                    ▲
                            ┌───────┴────────┐
                            │  RAG (Chroma)  │
                            │  408 chunks    │
                            │  HKMA + Cap 656│
                            └────────────────┘
   External: DeBank Cloud (cross-chain address profile) | Mock OFAC JSON
```

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for module-level IO contracts and the
full data-flow walkthrough.

---

## Tech stack

| Layer | Technology |
|---|---|
| Smart contract | Solidity 0.8.24, OpenZeppelin v5.6.1, Foundry 1.5 |
| Chain | Arc Testnet (chain ID 5042002, gas in USDC) |
| Agent reasoning | Google **Gemini 2.5 Pro** + **Gemini 2.5 Flash** via `google-genai` SDK |
| Embeddings / RAG | **Gemini `gemini-embedding-2`** (3072-dim) + **Chroma** (persistent SQLite-backed) |
| Cross-chain profiling | **DeBank Cloud Pro API** (85+ chains) |
| Sanctions screening | Local JSON registry mirroring OFAC/HKMA gazette schema (production hot-swappable) |
| Sentinel signing | **Circle Wallets Developer-Controlled API** (MPC) |
| Backend | FastAPI + SSE (sse-starlette) + SQLModel (SQLite audit log) |
| Frontend | Vanilla HTML / CSS / JS — no build step |

---

## Circle products integrated

| Product | Integration level | Where in code |
|---|---|---|
| **USDC** | Native gas token on Arc; MockUSDC mirrors the regulated-asset interface (mint/burn/freeze/transfer) | `contracts/src/MockUSDC.sol`; Arc faucet for testnet USDC |
| **Wallets (Developer-Controlled)** | **Real MPC integration**: sentinel wallet is created via Circle's Wallet Set API; every freeze/refund/quarantine tx is signed via Circle's MPC, not a local keystore | `backend/chain/circle_wallets.py`, `backend/chain/executor.py::CircleWalletsSigner` |
| **CCTP + BridgeKit** | Architectural integration via `CCTPInflowContext` simulator; pipeline treats CCTP-tagged inflows with cross-border tags so RAG retrieves Para 6.40–6.42 | `backend/crosschain/cctp_simulator.py`; scenario `cctp_inflow_ethereum` |
| **Gateway** | Referenced as the unified USDC liquidity layer above CCTP in architecture; not directly invoked in MVP (acknowledged in `docs/circle_product_feedback.md`) | architecture diagram only |
| **Nanopayments** | Not integrated — not relevant to AML enforcement narrative |

---

## Regulatory anchors

Every code path is traceable to a specific HKMA Guideline paragraph or Cap 656
section. See [`TRACEABILITY.md`](./TRACEABILITY.md) for the complete matrix.

Key anchors:

- **HKMA Para 5.10(c)** — On-chain freeze capability requirement → `MockUSDC.freezeAddress`
- **HKMA Para 5.11** — Cautious approach under proof-of-effectiveness uncertainty (project's raison d'être)
- **HKMA Para 5.7** — Written justification of grounds for suspicion → Reporter agent
- **HKMA Para 6.40–6.42** — P2P unhosted-wallet cross-border rules → CCTP scenario
- **HKMA Para 7.2–7.5** — Sanctions screening → SanctionsRegistry
- **Cap 656 s.171** — Statutory basis for the HKMA Guideline itself

---

## Repository layout

```
StablecoinChallenge/
├── README.md                        ← you are here
├── ARCHITECTURE.md                  ← detailed module + data-flow architecture
├── TRACEABILITY.md                  ← Para → feature → file → test matrix
├── .env.example                     ← required environment variables
│
├── contracts/                       ← Solidity (Foundry)
│   ├── src/MockUSDC.sol             ← ERC20 + sentinel role + freeze/refund/quarantine
│   ├── test/MockUSDC.t.sol          ← 18 unit tests
│   ├── script/Deploy.s.sol          ← Arc testnet deploy script
│   └── foundry.toml
│
├── backend/                         ← Python (FastAPI + agents)
│   ├── main.py                      ← FastAPI app, SSE, /demo/trigger
│   ├── config.py                    ← typed env loader
│   ├── agent/
│   │   ├── manager.py               ← orchestrator (no LLM)
│   │   ├── risk_assessor.py         ← Gemini flash; outputs RiskProfile
│   │   ├── compliance_decider.py    ← Gemini pro; picks Action + cited paragraphs
│   │   └── reporter.py              ← Gemini pro; writes markdown XAI
│   ├── chain/
│   │   ├── listener.py              ← web3.py Transfer event subscription
│   │   ├── circle_wallets.py        ← Circle Developer-Controlled Wallets client
│   │   ├── executor.py              ← TxSigner protocol + dispatching
│   │   └── abi/MockUSDC.json
│   ├── rag/
│   │   ├── ingest.py                ← chunk + embed HKMA + Cap 656 into Chroma
│   │   └── retrieve.py              ← top-K retrieval
│   ├── data/
│   │   ├── debank_client.py         ← cross-chain address profile
│   │   ├── sanctions.py             ← local registry
│   │   └── sanctions_mock.json
│   ├── crosschain/
│   │   └── cctp_simulator.py        ← CCTP inflow context for cross-border scenarios
│   ├── store/
│   │   ├── audit_log.py             ← SQLite append-only log
│   │   └── models.py                ← Pydantic IO contracts
│   └── cli/m2_demo.py               ← reproducible end-to-end script (for video recording)
│
├── dashboard/                       ← vanilla HTML/JS dashboard
│   ├── index.html
│   ├── app.js
│   └── style.css
│
├── docs/
│   ├── deployment.md                ← deployment record (contract addresses, demo wallets)
│   └── circle_product_feedback.md   ← MANDATORY submission section: Circle product UX feedback
│
├── scripts/
│   └── register_entity_secret.py    ← one-time Circle entity-secret encryption helper
│
└── _extracted/                      ← regulatory corpus (text, not committed binaries)
    ├── aml_guideline.txt            ← HKMA AML/CFT Guideline (Aug 2025)
    └── cap656.txt                   ← Stablecoins Ordinance (Cap 656, 01-08-2025)
```

---

## Roadmap

| Stage | Status | Notes |
|---|---|---|
| M1 — chain plumbing (deploy + listen) | ✅ done | MockUSDC deployed on Arc Testnet; 18/18 contract tests pass |
| M2 — single-agent decision + on-chain freeze | ✅ done | Verified freeze tx on Arc via Circle Wallets MPC |
| M3 — RAG + 4 sub-agent split + dashboard | ✅ done | 408 RAG chunks; agent citations grounded |
| M4 — cross-chain scenarios + traceability + docs | ✅ done (in progress: error-hardening) | this milestone |
| M5 — submission package: deploy + video | ⏳ next | hosted demo URL + 3-min walkthrough video |
| **Future** | | distillation to a domain-specific small model (post-MVP); RLCF with real MLRO feedback (long term) |

---

## License

MIT. Regulatory excerpts in `_extracted/` are Hong Kong Government / HKMA publications,
quoted under fair use for compliance research.

---

> *Generated by the team for the HK Stablecoin Challenge 2026 — Track 4: Agentic Economy.*
