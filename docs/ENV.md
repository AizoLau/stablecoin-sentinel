# Environment Variables Dictionary

All environment variables consumed by the backend, with purpose, required/optional
status, example value, and where to obtain it.

Variables are loaded via `python-dotenv` from a `.env` file at the project root
into the `Settings` model in `backend/config.py`. The Render Blueprint
(`render.yaml`) injects them at deploy time.

| ⚠️ Status legend |  |
|---|---|
| 🔴 Required | Backend will fail to start or fail at first request without it. |
| 🟡 Required-for-feature | Specific feature (e.g. on-chain enforcement) won't work, but the backend boots. |
| 🟢 Optional | Has a sensible default. |

---

## Chain (Arc Testnet)

| Variable | Status | Example | Source | Purpose |
|---|---|---|---|---|
| `ARC_RPC_URL` | 🔴 | `https://rpc.testnet.arc.network` | Arc docs | Primary JSON-RPC endpoint. Used by `web3.py` (executor, listener, /health balance probe). |
| `ARC_CHAIN_ID` | 🟢 | `5042002` | Arc docs | Chain ID for Arc Testnet. Defaults to `5042002`. |
| `ARC_RPC_URL_ALCHEMY` | 🟢 | `https://arc-testnet.g.alchemy.com/v2/<key>` | https://alchemy.com | Secondary RPC for failover. Not yet wired into runtime (placeholder for future dual-provider). |
| `ARC_RPC_URL_QUICKNODE` | 🟢 | `https://...quiknode.pro/...` | https://quicknode.com | Tertiary RPC. Same caveat as above. |
| `ARC_EXPLORER_URL` | 🟢 | `https://explorer.testnet.arc.network` | Arc docs | Base URL for tx links in API responses and dashboard. Defaults shown. |

---

## Google Gemini (agent reasoning)

| Variable | Status | Example | Source | Purpose |
|---|---|---|---|---|
| `GEMINI_API_KEY` | 🔴 | `AQ.Ab8RN6Lic...` | https://aistudio.google.com/apikey | Used by all 4 LLM calls per decision (1 embedding + 3 generations). Free tier ~60 RPM. |
| `GEMINI_MODEL_PRO` | 🟢 | `gemini-2.5-pro` | hardcoded default | Model used by Compliance Decider + Reporter (the two heavyweight calls). |
| `GEMINI_MODEL_FLASH` | 🟢 | `gemini-2.5-flash` | hardcoded default | Model used by Risk Assessor (the lighter call). |

---

## DeBank Cloud (cross-chain address profiling)

| Variable | Status | Example | Source | Purpose |
|---|---|---|---|---|
| `DEBANK_ACCESSKEY` | 🔴 | `275565ce73eb9af3...` | https://cloud.debank.com → API keys | Authorization for DeBank Pro API. Called per decision by `RiskAssessor`. |
| `DEBANK_BASE_URL` | 🟢 | `https://pro-openapi.debank.com` | DeBank docs | Default fine. Override only for staging/test. |

---

## Circle Wallets (Developer-Controlled)

| Variable | Status | Example | Source | Purpose |
|---|---|---|---|---|
| `CIRCLE_API_KEY` | 🟡 | `TEST_API_KEY:0c2862...:b646ef...` | Circle Console → API Keys (Testnet env) | Bearer token for all Circle Wallets calls. Required for on-chain enforcement. |
| `CIRCLE_ENTITY_SECRET` | 🟡 | 64-char hex (32 bytes) | You generate locally with `secrets.token_hex(32)`, then register via `scripts/register_entity_secret.py` | Root key from which Circle derives per-wallet signing material. Each contractExecution call re-encrypts this with Circle's RSA public key (OAEP-SHA256). Loss = unrecoverable wallets. |
| `CIRCLE_WALLET_SET_ID` | 🟢 | `2263d432-dbc7-59da-8faf-0860c4f84f94` | Returned by `POST /v1/w3s/developer/walletSets` | Wallet Set containing the sentinel wallet. Not strictly required at runtime (we look up wallet by `CIRCLE_SENTINEL_WALLET_ID` directly) but useful for grouping. |
| `CIRCLE_SENTINEL_WALLET_ID` | 🟡 | `bc6eebee-5cc7-51dc-9512-d72c59487fa3` | Returned by `POST /v1/w3s/developer/wallets` | The Circle wallet that signs enforcement txs. Required for the executor. |
| `CIRCLE_SENTINEL_WALLET_ADDRESS` | 🟡 | `0x11afacf004f144db1df3857ee1ea555d233c33c7` | Returned by `POST /v1/w3s/developer/wallets` | The on-chain address. Used by `/health` for balance probe and by deployer to `grantRole(SENTINEL_ROLE, ...)`. |

---

## Deployer / demo wallets

These are local-keystore wallets used for **non-sentinel** operations: deploying
the contract, minting, unfreezing, simulating Alice's transfers. The sentinel
itself never uses local keys — it signs through Circle.

| Variable | Status | Example | Source | Purpose |
|---|---|---|---|---|
| `DEPLOYER_PRIVATE_KEY` | 🟡 | `0x2e6f...` (64 hex) | Generated via `cast wallet new` | Deploys the contract; receives `DEFAULT_ADMIN_ROLE` (OWNER); used by `_unfreeze_target` in the `/demo/trigger` unfreeze path. |
| `DEPLOYER_ADDRESS` | 🟢 | `0x1a7F...` | Derived from the private key | Convenience; saved to avoid re-derivation. |
| `SENTINEL_PRIVATE_KEY` | 🟢 | `0x6c8a...` | Generated via `cast wallet new` | Local-keystore fallback signing key. **Not used in M5 demo path** (Circle Wallets is the active signer). Kept for `LocalKeystoreSigner` if you switch away from Circle. |
| `SENTINEL_ADDRESS` | 🟢 | `0xE14E...` | Derived | Same caveat. |
| `DEMO_ALICE_PRIVATE_KEY` | 🟢 | `0x5018...` | Generated | Sends the synthesized P2P transfer in scenarios. |
| `DEMO_ALICE_ADDRESS` | 🟡 | `0x6F10...` | Derived | Default `from_address` for `/demo/trigger`. |
| `DEMO_BOB_PRIVATE_KEY` | 🟢 | `0xb573...` | Generated | Bob doesn't sign anything (he's the recipient), but you can use this if you want to test Bob attempting a transfer after being frozen. |
| `DEMO_BOB_ADDRESS` | 🟡 | `0x0F7B...` | Derived | Default `to_address` for `/demo/trigger`. |
| `DEMO_RECOVERY_PRIVATE_KEY` | 🟢 | `0xa468...` | Generated | Recovery wallet for `QUARANTINE` action. Doesn't sign. |
| `DEMO_RECOVERY_ADDRESS` | 🟡 | `0x92da...` | Derived | Where quarantined funds go. Required for the QUARANTINE action path. |

### Why local keystore for these but Circle for sentinel

Sentinel is the security-critical role — losing its key = enforcement-action
forgery, the agent equivalent of "issuer compromise". Hence MPC.

Deployer and demo wallets are testnet-only convenience accounts. Their loss
would just mean re-funding from a faucet. Local keystore is fine.

---

## Contracts

| Variable | Status | Example | Source | Purpose |
|---|---|---|---|---|
| `MOCK_USDC_ADDR` | 🔴 | `0xA43143DF2C00Bce848af35eF4Cb69911Ae37d95B` | Returned by `forge script Deploy.s.sol --broadcast` | Address of the deployed MockUSDC contract. Required by listener, executor, and the unfreeze path. |

---

## Backend runtime

| Variable | Status | Example | Source | Purpose |
|---|---|---|---|---|
| `LOG_LEVEL` | 🟢 | `INFO` | choose | One of `DEBUG / INFO / WARNING / ERROR`. Default `INFO`. |
| `SQLITE_PATH` | 🟢 | `./audit.db` (local) or `/tmp/audit.db` (Render) | choose | Where the append-only audit log lives. Render free tier has no persistent disk; `/tmp` resets on each restart. |
| `SSE_HEARTBEAT_SECONDS` | 🟢 | `15` | choose | Interval between SSE heartbeat events. Set lower if your CDN/proxy is aggressive about closing idle streams; higher to reduce traffic. |

---

## RAG (Chroma)

| Variable | Status | Example | Source | Purpose |
|---|---|---|---|---|
| `RAG_CHROMA_PATH` | 🟢 | `./chroma_db` | choose | Directory where Chroma persists its SQLite + vector files. Bundled into the Docker image (~11 MB) so cold start doesn't re-ingest. |
| `RAG_COLLECTION_NAME` | 🟢 | `hkma_aml_guideline` | choose | Chroma collection name. Both `ingest.py` and `retrieve.py` reference this. Change only if you want multiple collections side-by-side. |
| `SANCTIONS_JSON_PATH` | 🟢 | `backend/data/sanctions_mock.json` (computed default) | choose | Path to the local sanctions registry. Override to point at a production-fetched list. |

---

## Quick-fill workflow

If you're cloning the repo for the first time, here's the minimum to get to a
working `/demo/trigger`:

```ini
# Copy .env.example to .env, then fill in just these five:
GEMINI_API_KEY=<from aistudio.google.com>
DEBANK_ACCESSKEY=<from cloud.debank.com>
CIRCLE_API_KEY=<from console.circle.com>
CIRCLE_ENTITY_SECRET=<32-byte hex you generated>
CIRCLE_SENTINEL_WALLET_ID=<UUID from your wallet creation>

# These point at our deployed instance — works out-of-the-box for read-only inspection:
MOCK_USDC_ADDR=0xA43143DF2C00Bce848af35eF4Cb69911Ae37d95B
CIRCLE_SENTINEL_WALLET_ADDRESS=0x11afacf004f144db1df3857ee1ea555d233c33c7
DEMO_ALICE_ADDRESS=0x6F106e2D89B58FEC6Fa1037Fd6e2cEAa586F7d59
DEMO_BOB_ADDRESS=0x0F7Ba243461ba7E5043383E9D4D9B96AE8b02201

# All other values use sensible defaults from backend/config.py.
```

To actually submit on-chain enforcement, you also need:
- Your Circle wallet funded with testnet USDC (https://faucet.circle.com)
- Your Circle wallet granted `SENTINEL_ROLE` on `MOCK_USDC_ADDR` (requires
  `DEPLOYER_PRIVATE_KEY` from the original deployer — which is in our `.env`
  but won't be in yours; you'd redeploy or coordinate)

The easiest end-to-end path is: redeploy MockUSDC with your own `DEPLOYER_PRIVATE_KEY`,
update `MOCK_USDC_ADDR`, then `grantRole(SENTINEL_ROLE, your_circle_wallet)`.
See `docs/CONTRACTS.md::Deployment`.

---

## Secrets handling

- **`.env` is `.gitignored`**. It's only on your local machine and on the
  Render Blueprint's secret store.
- **Recovery file** (Circle entity secret recovery) is also `.gitignored`
  as `recovery_file.dat` / `*.pem`. **Back this up separately** — it's the
  only way to recover sentinel-wallet signing capability if you lose the
  entity secret.
- **Private keys committed in this repo's history**: these are **testnet-only
  wallets**, generated via `cast wallet new`, with zero value beyond the
  faucet allocation. They're treated as demo data, not secrets. Do NOT reuse
  them on mainnet.
