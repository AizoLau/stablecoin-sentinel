# Circle Product Feedback

*Mandatory submission chapter for the HK Stablecoin Challenge.*

This document is honest, first-person feedback from a team that built an end-to-end
agentic compliance system on Circle's stack in roughly two days. It is structured
around the four Circle products we integrated (or intentionally did not integrate),
plus a meta-section on developer experience.

The whole project exists because of one HKMA paragraph:

> "As the effectiveness of these risk mitigating measures is yet to be proven, the
> HKMA expects licensees to adopt a cautious approach in determining whether their
> systems are adequate for mitigating ML/TF risks associated with licensed stablecoin
> activities, in particular as regards peer-to-peer transfers between unhosted wallets."
> — **HKMA AML/CFT Guideline Para 5.11**

Everything below should be read in that context: we were building *the* missing
piece — autonomous on-chain enforcement that demonstrates cautious-approach
effectiveness — and we did it on Circle's rails.

---

## USDC on Arc Testnet

### What worked

- **USDC-as-gas was a delightful surprise.** Once we wrapped our head around it,
  having gas denominated in USDC made `cast balance` immediately interpretable
  ("0x... has 19.99 USDC of gas") and removed the cognitive overhead of
  managing ETH faucets separately from USDC operations.
- The Circle Testnet Faucet (`faucet.circle.com`) is excellent: no Discord
  captcha, no social login, just paste address → 20 USDC. We funded 6 wallets in
  ~3 minutes total.
- Arc Testnet RPC at `rpc.testnet.arc.network` is reliable; chain ID 5042002 is
  fully EVM-compatible and Foundry deploy worked first try.

### What would improve

- **`cast balance` returns 18-decimal `wei`-style numbers** for USDC gas, but the
  USDC standard everywhere else (token transfers, mint, freeze) is 6 decimals.
  This forced us to remember a special case ("Arc gas is 18-decimal even though
  USDC is 6-decimal") that other EVM chains do not have. Documenting this
  prominently on the Arc Quickstart page would save every team the same
  head-scratch we had on Day 1.
- **Arc Block Explorer URL convention** could be more discoverable from the RPC
  metadata. We had to find it indirectly. Returning the explorer base URL via
  `eth_chainSpec` or a Circle developer endpoint would be cleaner than
  hard-coding it in `.env`.

---

## Wallets (Developer-Controlled API)

This was the **highest-friction integration** in the project, but also the most
valuable once it worked. We document the friction explicitly so future teams
benefit.

### What worked

- Once the entity secret was registered and the wallet was created, **everything
  worked exactly as documented**. `POST /v1/w3s/developer/transactions/contractExecution`
  succeeded on the first valid request (after we fixed the `feeLevel` format,
  see below). The wallet was `LIVE` on Arc Testnet immediately and signed our
  first `freezeAddress` call within seconds.
- **`ARC-TESTNET` is in the supported blockchains list**, which we want to call
  out explicitly: when Arc launched its public testnet in October 2025, Circle
  Wallets did not yet support it — by the time we built (May 2026) it was
  fully wired up. This is great responsiveness.
- The MPC architecture is the right answer for "the agent's signing key should
  not be compromisable by an LLM exploit alone". We were able to build a
  security narrative around "three-layer protection: contract role isolation +
  Circle MPC + application-layer rate limits" that would not have been possible
  with a local keystore.

### What would improve

#### Console UX — Configurator section is confusing

The Configurator page has three columns: **USER CONTROLLED**, **DEV CONTROLLED**,
**MODULAR WALLETS**, each with its own Configurator / Wallets / Transactions
sub-pages. As a developer who only wants to build with Developer-Controlled
Wallets, this took us ~15 minutes to navigate:

- The top of the page shows the **User Controlled Configurator** (App ID +
  Authentication Methods), which is not what we needed.
- We clicked through every subsection before realizing **DEV CONTROLLED → Configurator**
  was the entity-secret registration page we were looking for.

Suggestion: when a Developer Account is created with the "Developer-Controlled
Wallets" capability, the Configurator landing page should highlight that column
or auto-navigate. The other two product lines (User Controlled, Modular Wallets)
could be collapsed behind a "More products" disclosure.

#### Entity secret registration — public key endpoint is undocumented in the Console

The Console's Entity Secret form expects a 684-character ciphertext (RSA-OAEP-SHA256
of the 32-byte secret, encrypted with Circle's public key, base64-encoded). But
the Console **does not give you the public key** — it expects you to fetch it via
`GET /v1/w3s/config/entity/publicKey` with a Bearer API key.

This works fine programmatically, but a first-time developer reads the form
("paste 684-character ciphertext") and has no path to produce one without
reading the Wallets SDK source. We wrote our own encryption script
(`scripts/register_entity_secret.py`) — happy to share, but **a "Generate
ciphertext in browser" button or an inline code snippet on the Entity Secret
page would save every team this detour.**

#### `contractExecution` API — the `fee` field shape

Our first `POST /v1/w3s/developer/transactions/contractExecution` returned:

```json
{
  "code": 2,
  "message": "API parameter invalid",
  "errors": [
    {"location": "gasPrice", "message": "'gasPrice' field may not be empty when 'FeeLevel PriorityFee MaxFee' fields are not set"},
    {"location": "gasLimit", "message": "'gasLimit' field may not be empty when 'FeeLevel' field is not set"}
  ]
}
```

We had sent `"fee": {"type": "level", "config": {"feeLevel": "MEDIUM"}}` — the
shape documented in older blog posts and several community Gists. The correct
shape is `"feeLevel": "MEDIUM"` at the top level. We figured it out by reading
the error message carefully, but it cost us 10 minutes. The Wallets API
reference page on developers.circle.com is up-to-date; the discoverable
community examples are not. **A short "Common mistakes" / "If you see error
code 2" section in the docs would help.**

#### Recovery file UX

After registering an entity secret, the Console correctly prompts to download a
recovery file. The wording "this is the ONLY way to recover wallets if you lose
the entity secret" is correctly alarming. We saved the file but were uncertain
about *how* one would use it — there is no recovery flow in the Console UI that
we could find. A linked "How to use this recovery file" doc on the same page
would close the loop.

---

## CCTP + BridgeKit

### What we did

We did **not** invoke CCTP at the smart-contract level on testnet. Instead, we
built a software-level CCTP simulator (`backend/crosschain/cctp_simulator.py`)
that produces structured "this transfer originated from Ethereum mainnet via
CCTP and the sender has Tornado-Cash-relay history" context. This context flows
through the same Risk Sentinel pipeline and causes the agent to retrieve
HKMA Para 6.40-6.42 (cross-border unhosted-wallet rules) instead of the on-Arc
freeze cluster.

### Why we didn't do real CCTP burn-mint on testnet

For our use case — a sentinel watching unhosted-wallet inflows on Arc — the
*signal* we need is "CCTP receive event with source-chain metadata". Real CCTP
burn-and-mint requires the canonical USDC contract on both source and
destination chains, and we cannot control USDC's mint authority. We could have
deployed an additional `CCTPReceiver` mock contract that emits a
`CCTPReceived(recipient, sourceChain, ...)` event the listener would pick up,
but this would add deployment complexity for a signal that doesn't change the
agent's reasoning.

### What we'd love to see

- **A "CCTP Simulator" SDK or contract on Arc Testnet** that the Circle team
  ships, mimicking the message-transmission semantics of real CCTP. Today every
  team rolls its own simulator; a canonical one would let us all share
  test-event payloads and would dovetail with the Arc Testnet Faucet's
  developer-facing pitch.
- **CCTP attestation API on testnet** — even mocked — so we could exercise the
  full burn-attest-mint flow without deploying our own MessageTransmitter
  replacement.

---

## Gateway

We integrated Gateway **at the architectural level only**: it appears in our
README's Circle products table and in `ARCHITECTURE.md`'s deployment topology
diagram as the unified USDC liquidity layer above CCTP. We did not invoke any
Gateway API.

The honest reason: our project is a single-link enforcement loop on Arc. Gateway
shines for multi-chain liquidity routing — a layer above the single-chain
enforcement we're doing. The natural integration would be "after a quarantine,
move the quarantined funds back to the source chain via Gateway" — but that's a
future-work item, not MVP-scope.

We mention this honestly so the Circle team knows that "checking Gateway on the
product list" is not always a real integration on day one — and that's OK if
the architecture acknowledges where it would slot in.

---

## Nanopayments

Not integrated. We considered it for "charge the agent per LLM inference call"
but the narrative doesn't hold: the agent is internal to the licensee, not a
third-party service, so there is no counterparty to nanopay. We'd be interested
to see Circle publish reference use cases of Nanopayments that go beyond
"AI inference paywall" — e.g., paying for sanctions-list API access on a
per-query basis would be a natural fit for our SanctionsRegistry.

---

## Meta: developer experience

### What was excellent

- **Documentation links from `developers.circle.com` to actual API references are correct.**
  In the era of broken-link wikis, this matters.
- **The Circle Developer Console (Beta) UI is fast and responsive.** Loading the
  Wallets sub-page is sub-second even from Asia.
- **The Anthropic-vs-Gemini API contrast** (this is a sidebar but matters): we
  briefly considered Anthropic Claude as the agent backend before standardizing
  on Gemini. Circle's products do not lock us into either — no preferred SDK,
  no preferred LLM bridge. That openness is the right call.

### What we wish existed

- **An "Arc + Wallets quickstart"** that walks through: register Developer
  Account → generate entity secret → create wallet on `ARC-TESTNET` → fund via
  faucet → sign a transaction. End-to-end in under 10 minutes. We pieced this
  together from four separate doc pages.
- **A reference repository** — even a stub — showing the **complete** flow from
  contract deployment on Arc through Wallets-signed enforcement actions. The
  current docs cover each step individually; a glued-together example is the
  fastest way for teams to validate they have the whole stack working before
  building business logic on top.
- **A Slack/Discord channel staffed by Circle engineers during hackathon
  weeks.** We hit one ambiguity (the `feeLevel` shape above) that would have
  been a 30-second resolution by a Circle engineer; we resolved it in 10 minutes
  on our own which was tolerable for this team but might block teams with less
  API debugging experience.

---

## Closing

We built this project to test a thesis: **the Para 5.11 cautious-approach gap can be
closed with an agentic on-chain compliance loop, and Circle's stack — USDC on
Arc + Developer-Controlled Wallets + (architecturally) CCTP — is the right
infrastructure to host it.**

The thesis holds. The agent reliably freezes designated parties on Arc within
~25 seconds end-to-end, every action is paragraph-traceable to HKMA Guideline
+ Cap 656, and Circle Wallets' MPC means the signing key is not a single point
of failure even if the agent is compromised.

We're shipping this MVP. We hope Circle ships the Wallets onboarding improvements
above, because the building experience is otherwise excellent and the
infrastructure is exactly what the regulated stablecoin industry needs.
