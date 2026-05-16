# Ignyte Submission Fill-In Guide

The HK Stablecoin Challenge requires 9 mandatory submission items. This file
has copy-paste-ready content for each one so you don't have to compose under
deadline pressure. Open Ignyte's submission form in one tab, this file in
another, paste.

Once you've actually filled the Ignyte form, **come back here and replace any
TODO with the real values** (e.g. video URL, demo URL) so the file stays as a
record of what was submitted.

| # | Item | Status |
|---|---|---|
| 1 | Title + short description | ✅ ready below |
| 2 | Track selection | ✅ Track 4 — Agentic Economy |
| 3 | Circle Developer Account email | ✅ aizolau0309@outlook.com |
| 4 | Circle product checklist | ✅ USDC + Wallets + CCTP+BridgeKit + Gateway |
| 5 | Functional MVP + architecture diagram | ✅ GitHub repo + ARCHITECTURE.md |
| 6 | Video demo | ⏳ TODO — record + upload |
| 7 | GitHub repo URL + README | ✅ https://github.com/AizoLau/stablecoin-sentinel |
| 8 | Demo URL | ⏳ TODO — Render deploy |
| 9 | Circle Product Feedback | ✅ docs/circle_product_feedback.md (or paste below) |

---

## 1. Title + short description

### Title (recommended ≤ 60 characters)

```
Unhosted Wallet Risk Sentinel — autonomous on-chain AML on Arc
```

(57 characters)

### Alternative shorter title (≤ 50 chars)

```
HK Stablecoin Risk Sentinel for Unhosted Wallets
```

(47 characters)

### Short description (recommended ≤ 280 characters — Twitter-length)

```
Autonomous AML/CFT agent that monitors USDC P2P transfers on Circle Arc Testnet, evaluates risk via Gemini + RAG over the HKMA Guideline, and executes on-chain enforcement (freeze / refund / quarantine) through Circle Wallets MPC. Closes the Para 5.11 cautious-approach gap.
```

(276 characters)

### Longer description (if Ignyte allows ≤ 1000 characters)

```
The HKMA's August 2025 AML/CFT Guideline for Licensed Stablecoin Issuers acknowledges in Para 5.11 that the effectiveness of unhosted-wallet risk-mitigating measures is "yet to be proven". Existing tools either score risk (Chainalysis) or run user wallets (MetaMask). Nothing closes the loop between risk decision and on-chain enforcement.

The Risk Sentinel is that closing loop. A four-stage agent pipeline — Risk Assessor (Gemini Flash) → Compliance Decider (Gemini Pro) → Reporter (Gemini Pro) → Executor (Circle Wallets MPC) — monitors P2P USDC transfers on Arc Testnet, retrieves the most relevant HKMA paragraphs via Chroma RAG (149 HKMA paragraphs + 259 Cap 656 pages), and submits freeze / refund / quarantine transactions in under 25 seconds end-to-end.

Every citation is verifiably retrieved (not hallucinated). Every signing key is MPC-managed. Every decision is paragraph-traceable to HKMA Guideline + Cap 656.
```

(975 characters)

---

## 2. Track selection

**Track 4 — Agentic Economy**

Rationale (if asked): the project demonstrates an autonomous on-chain agent
that makes compliance decisions and executes blockchain transactions without
per-action human approval, using Circle's stablecoin infrastructure.

---

## 3. Circle Developer Account email

```
aizolau0309@outlook.com
```

This is the email registered with Circle Console for the
Developer-Controlled Wallet that signs all enforcement actions.

---

## 4. Circle product checklist

Tick these four:

- ☑ **USDC** — native gas token on Arc; MockUSDC mirrors USDC's interface at the regulated-asset level
- ☑ **Wallets** — Developer-Controlled Wallets API with real MPC signing on Arc Testnet (`CIRCLE_SENTINEL_WALLET_ADDRESS = 0x11afacf004f144db1df3857ee1ea555d233c33c7`)
- ☑ **CCTP + BridgeKit** — cross-chain inflow simulator + risk-tag injection for cross-border scenarios; architectural integration documented in `ARCHITECTURE.md`
- ☑ **Gateway** — referenced as the unified USDC liquidity layer above CCTP in architecture; integration is architectural in MVP (acknowledged in `circle_product_feedback.md`)

Do **not** tick:
- ☒ Nanopayments — not relevant to AML enforcement narrative; explicitly excluded with rationale in `circle_product_feedback.md`

---

## 5. Functional MVP + architecture diagram

**Repo URL**: https://github.com/AizoLau/stablecoin-sentinel

**Architecture diagram**:
- Primary: ASCII diagram in [`ARCHITECTURE.md`](https://github.com/AizoLau/stablecoin-sentinel/blob/master/ARCHITECTURE.md#high-level-diagram)
- Secondary: README "Architecture" section

**MVP runnable proof**:
- 18/18 Foundry tests passing
- End-to-end reproducible demo: `python -m backend.cli.m2_demo --unfreeze-first` produces a real on-chain freeze tx on Arc Testnet within 25 seconds
- Sample deployed freeze tx: https://explorer.testnet.arc.network/tx/0xee780d8c02fdea8fb225e3b14a1c1e7bc614b5a030c7cf43c4893c0cbb91b066

---

## 6. Video demo

**Video URL**: ⏳ TODO — fill in after recording

Recording follows `docs/demo_script.md`. Target length 3:30, hard cap 4:00.

Suggested video title:

```
HK Stablecoin Risk Sentinel — Autonomous AML on Circle Arc (3 min demo)
```

Suggested video description (paste into Loom / YouTube description field):

```
A 3-minute demo of an autonomous AML/CFT compliance agent built for the HK
Stablecoin Challenge Track 4 (Agentic Economy).

What you'll see:
- HKMA Para 5.11 "cautious approach" framing
- Three live scenarios on Arc Testnet:
  1. Sanctioned recipient → FREEZE
  2. CCTP cross-chain inflow → FREEZE with cross-border citations
  3. Clean transfer → PASS
- Real on-chain transactions signed by Circle Wallets MPC API
- Every citation retrieved from RAG over the full HKMA Guideline + Cap 656

Stack: Circle Arc Testnet + Circle Wallets + USDC + CCTP, Gemini 2.5 Pro/Flash,
Chroma RAG, FastAPI + vanilla JS dashboard.

Repo: https://github.com/AizoLau/stablecoin-sentinel
Architecture: https://github.com/AizoLau/stablecoin-sentinel/blob/master/ARCHITECTURE.md
Regulatory traceability: https://github.com/AizoLau/stablecoin-sentinel/blob/master/TRACEABILITY.md
```

---

## 7. GitHub repository

**URL**: https://github.com/AizoLau/stablecoin-sentinel

**README highlights to point judges at**:

- Hero section ("Why this project exists") quotes HKMA Para 5.11 verbatim
- "Demo at a glance" table shows the three scenarios + paragraphs each cites
- "Quick start" gives a clone-to-running command sequence
- "Circle products integrated" table shows the four products
- Links to ARCHITECTURE / TRACEABILITY / CODE_TOUR / 4 reference docs

**Recursive clone instruction (mention if asked about reproducibility)**:

```bash
git clone --recursive https://github.com/AizoLau/stablecoin-sentinel.git
```

The `--recursive` flag pulls the OpenZeppelin and forge-std submodules pinned in
`.gitmodules`.

---

## 8. Demo URL (publicly accessible)

⏳ TODO — fill in after Render deploy

Once Render Blueprint apply is complete, the URL will be:

```
https://<your-service-name>.onrender.com/dashboard/
```

Suggested service name: `stablecoin-sentinel` (default from `render.yaml`).

So the URL will likely be:

```
https://stablecoin-sentinel.onrender.com/dashboard/
```

(may have a suffix like `-abc123` if the name is taken).

**Demo URL operating instructions to include in the submission text**:

```
Open the URL. The dashboard loads with three scenario buttons:
1. "🔒 Sanctioned recipient (FREEZE)"
2. "🌉 CCTP inflow from Ethereum (cross-border FREEZE)"
3. "✅ Clean transfer (PASS)"

Click any button. Within ~25 seconds a decision card appears showing the agent's
action, the cited HKMA paragraphs (with full text expandable inline), the
reasoning, and a link to the on-chain transaction on Arc Explorer.

The "unfreeze recipient first" checkbox (ticked by default) allows replaying the
same scenario without redeploying.

Note: Render's free tier sleeps after 15 minutes idle. First request after sleep
takes ~30 seconds to wake. If the page is slow to first load, give it a moment.
```

---

## 9. Circle Product Feedback

Paste the full content of [`docs/circle_product_feedback.md`](https://github.com/AizoLau/stablecoin-sentinel/blob/master/docs/circle_product_feedback.md) into the Ignyte form's feedback field.

If Ignyte has a character limit and the full doc doesn't fit, use this summary version (≤ 2500 characters):

```
Circle Product Feedback — Unhosted Wallet Risk Sentinel team

USDC on Arc Testnet: USDC-as-gas was a delightful surprise. The Circle Testnet Faucet (faucet.circle.com) was excellent — no captcha, immediate funding. One friction: cast balance returns 18-decimal wei-style numbers for USDC gas, but USDC standard everywhere else is 6 decimals. Documenting this prominently on the Arc Quickstart would save every team the same head-scratch.

Wallets (Developer-Controlled): The highest-friction integration but the most valuable. ARC-TESTNET is in the supported blockchains list and worked flawlessly once registered. Three Console UX improvements would help:
1) The Configurator page mixes User-Controlled, Dev-Controlled, and Modular Wallets — a developer who only wants Dev-Controlled wastes 15 min navigating.
2) Entity Secret form expects 684-char ciphertext but Console doesn't provide a "Generate ciphertext in browser" button — devs must read SDK source.
3) The fee field shape in contractExecution — error message says "FeeLevel" but several community Gists show "fee.config.feeLevel" (deprecated). Updated examples in error responses would close the gap.

Recovery file: correctly alarming UX but no documented "How to use this" flow. A linked recovery how-to would close the loop.

CCTP+BridgeKit: We did software-level simulation (cctp_simulator.py) because real CCTP burn-mint requires controlling USDC mint, which we cannot do as third-party devs. Suggestion: ship a CCTP Simulator SDK on Arc Testnet that mimics the message-transmission semantics, so every team doesn't roll their own.

Gateway: Architectural integration only; the natural use case for our project (post-quarantine cross-chain return) is future work. We mention this honestly.

Nanopayments: Not integrated — narrative doesn't fit AML/CFT enforcement. Would be interested in reference use cases beyond AI-inference paywalls.

Overall developer experience excellent. Docs link to actual API references correctly. Console is fast. An "Arc + Wallets quickstart" walking through register → entity secret → wallet creation → first signed tx in under 10 minutes would be the highest-leverage doc improvement.

Full feedback: https://github.com/AizoLau/stablecoin-sentinel/blob/master/docs/circle_product_feedback.md
```

(2480 characters)

---

## Submission checklist (run before clicking Submit)

- [ ] Render demo URL responds to `/health` with `ok: true`
- [ ] Dashboard at `/dashboard/` loads, three scenario buttons clickable
- [ ] One click of "🔒 Sanctioned recipient" produces a freeze tx visible on Arc explorer
- [ ] Video uploaded to Loom / YouTube, **public or unlisted** (not private), URL pasted in section 6
- [ ] GitHub repo is **PUBLIC** (verify in incognito tab — should clone without auth)
- [ ] README renders correctly on GitHub (open the file in the GitHub UI)
- [ ] `ARCHITECTURE.md` + `TRACEABILITY.md` linked from README and render correctly
- [ ] Circle Product Feedback either pasted in the form OR clearly linked from README
- [ ] Submitter email matches the Circle Developer Account (Section 3)

---

## After submission

Save the submission confirmation page / receipt. If Ignyte sends a confirmation
email, archive it under "HK Stablecoin Challenge submission".

Update this file's TODO sections (video URL, demo URL) with the actual values
that were submitted. Commit + push. This is the historical record of what you
sent.
