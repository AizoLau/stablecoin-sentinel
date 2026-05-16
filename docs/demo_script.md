# Demo Video Script

Target length: **3 minutes 30 seconds** (hard cap 4:00). Tone: confident,
matter-of-fact. No emoji, no hype.

Recording setup
- Resolution: 1920 × 1080
- Microphone: any decent USB mic; record voice over **after** screen capture if
  retakes are needed
- Screen capture tool: OBS Studio (free) or Loom Desktop
- Browser: Chrome / Edge, zoom level 100%, window 1600 × 900
- Open these tabs in advance:
  1. `http://localhost:8000/dashboard/` (or hosted demo URL)
  2. `https://explorer.testnet.arc.network/address/0xA43143DF2C00Bce848af35eF4Cb69911Ae37d95B`
  3. `https://console.circle.com` → DEV CONTROLLED → Wallets (showing the sentinel wallet)
  4. `https://faucet.circle.com` (optional, for showing where USDC gas comes from)

Before pressing record
- [ ] Backend is running and `/health` returns `ok: true`, `sentinel_gas_low: false`
- [ ] `audit_count` is **0** (so the first decision is decision #1, visually clean)
  - If not zero, delete `audit.db` and restart uvicorn
- [ ] Dashboard loads with empty feed and live status dot green
- [ ] Run `python -m backend.cli.m2_demo --unfreeze-first` once before recording so
      Bob is not already frozen on Arc

---

## Section 1 — Hook + project thesis (0:00 – 0:30)

**Screen**: Dashboard at `/dashboard/`, empty feed visible. Camera cursor hovers
over the Para 5.11 quote in the footer.

**Voiceover**:

> "Hong Kong's August 2025 stablecoin AML guideline contains an unusual admission
> from the regulator. In paragraph 5-point-11, the HKMA states that the
> effectiveness of unhosted-wallet risk mitigating measures is, quote, 'yet to be
> proven'. Existing tools either score risk — like Chainalysis — or run user
> wallets — like MetaMask. Nothing closes the loop between a risk decision and
> the on-chain enforcement action that proves the cautious approach works. This
> project is that closing loop. Built on Circle Arc, Circle Wallets, and Gemini.
> Three demonstrations follow."

---

## Section 2 — Architecture in thirty seconds (0:30 – 1:00)

**Screen**: Brief flash of `ARCHITECTURE.md` diagram (5 seconds), then back to
dashboard. Optionally show the four sub-agent file names in VSCode side panel.

**Voiceover**:

> "The agent pipeline has four specialist roles. Risk Assessor — runs Gemini
> Flash — scores cross-chain wallet history pulled from DeBank Cloud across
> 85 chains. Compliance Decider — Gemini Pro — chooses one of four actions and
> cites HKMA paragraphs that a Chroma vector store retrieved from the full
> HKMA guideline plus Cap 656. Reporter — Gemini Pro again — writes a
> markdown justification. Executor signs and submits the enforcement
> transaction through Circle Wallets' MPC API to a MockUSDC contract on Arc
> Testnet. Every citation is retrieved, not hallucinated."

---

## Section 3 — Scenario 1: Sanctioned recipient (1:00 – 1:55)

**Screen actions**:

1. Click **🔒 Sanctioned recipient (FREEZE)** button. Button shows "Submitting
   on-chain action…"
2. **Wait ~20 seconds** while the pipeline runs. Speak while waiting.
3. Decision card appears. Hover over the FREEZE badge.
4. Scroll down to "HKMA paragraphs cited". Click **Para 5.10** to expand its full
   text in place.
5. Scroll down to "All retrieved evidence (top 8)" and expand it briefly to show
   that other paragraphs were retrieved but not cited.
6. Scroll to "On-chain execution". Click the Arc explorer link.
7. **Switch to Arc explorer tab**. Show the transaction succeeded, then click
   the contract address. Show the `frozen[Bob]` mapping = `true`.

**Voiceover**:

> "Scenario one. The recipient is a known mixer in our sanctions registry. The
> agent receives the transfer event, queries DeBank for cross-chain history,
> retrieves the eight most relevant HKMA paragraphs from RAG, and chooses to
> freeze. Notice on the dashboard that each cited paragraph — five-ten,
> six-twenty-nine, four-thirty-nine — expands inline to its full regulatory text.
> The other five retrieved paragraphs are shown below, marked as evidence the
> agent considered but did not cite. Now look at the on-chain transaction:
> Circle Wallets has MPC-signed our freeze call and submitted it to Arc.
> Block confirmed. The recipient address is now frozen at the contract level —
> any further attempt to send or receive USDC reverts."

---

## Section 4 — Scenario 2: CCTP inflow (1:55 – 2:35)

**Screen actions**:

1. Tick the "unfreeze recipient first" checkbox if not already checked.
2. Click **🌉 CCTP inflow from Ethereum** button.
3. Wait ~20 seconds.
4. New decision card appears at the top of the feed. Click it.
5. Scroll to paragraphs section. Look for **Para 6.42** or **6.41** in the
   cited or retrieved list. Expand one of them to show the cross-border rule.
6. Scroll to Reasoning panel — point out the words "Tornado Cash" or
   "cross-border" if Gemini surfaced them.

**Voiceover**:

> "Scenario two simulates a CCTP inflow from Ethereum mainnet. The recipient
> received USDC across-chain from an address with Tornado Cash relay history.
> The risk signal injected for this scenario is different — cross-chain CCTP
> source plus cross-border designated party. As a result, RAG now retrieves
> paragraphs six-forty through six-forty-two, which are HKMA's specific rules
> for peer-to-peer transfers between unhosted wallets — including the
> cross-border travel-rule application. The freeze still happens, but the
> reasoning is anchored on different regulations. This is how the same agent
> covers different scenarios without us hard-coding rules: the corpus and the
> retriever pick the law that applies."

---

## Section 5 — Scenario 3: Clean PASS (2:35 – 2:55)

**Screen actions**:

1. Click **✅ Clean transfer (PASS)** button.
2. Wait ~15 seconds.
3. New decision card with green PASS badge. Risk score ~20.
4. Notice on-chain execution status = "skipped" (no tx submitted).

**Voiceover**:

> "Scenario three is a clean transfer. Sanctions registry has no entry for the
> recipient. The agent issues PASS, risk score around twenty, and crucially
> sends nothing on-chain. The agent does not over-freeze. This matters for the
> Para 5-point-11 cautious approach — caution means false-positives are still a
> cost the licensee must measure."

---

## Section 6 — Circle product call-outs + close (2:55 – 3:30)

**Screen actions**:

1. Switch to Circle Console tab → DEV CONTROLLED → Wallets. Show the sentinel
   wallet on Arc Testnet, state LIVE.
2. Briefly hover the **wallet ID** field; do not zoom into the actual UUID.
3. Switch back to dashboard. Scroll to the Para 5.11 footer marquee.

**Voiceover**:

> "The signing wallet is a real Circle Developer-Controlled Wallet on Arc
> Testnet — created via the wallet-set API, MPC-signed, never exposing the
> private key. We integrated four Circle products: USDC as the regulated asset
> and as the native gas on Arc, Wallets for MPC enforcement, CCTP via the
> inflow context simulator, and Gateway architecturally above CCTP. Full
> feedback in `circle_product_feedback.md` — including the small Console UX
> friction we hit, with concrete suggestions. To close: this is what
> autonomous on-chain compliance looks like when you take Para 5-point-11
> seriously. Every action is paragraph-traceable, every signing key is
> MPC-managed, every decision is loggable and auditable. Submitted for the
> Track 4 Agentic Economy. Thank you."

---

## Backup / re-take prompts

If a take goes long or a Gemini call is slow:
- Cut Section 4 (CCTP inflow). The story still works with Scenario 1 + Scenario 3.
- Compress Section 2 (Architecture) to 15 seconds: "Four specialist Gemini
  sub-agents, RAG over the full HKMA guideline plus Cap 656, signed via Circle
  Wallets MPC, settled on Arc."

If a freeze tx fails to confirm within 30 seconds:
- Mention the audit log behavior: "Even when Circle is slow, the audit row is
  written with execution status and error so an auditor sees exactly what
  happened." Switch to /decisions JSON if needed.

If a scenario doesn't trigger FREEZE as expected:
- The agent is non-deterministic; re-run. The Para 5.11 cautious approach
  means the agent is biased toward caution but not toward forced FREEZE. A
  QUARANTINE or REFUND result is still on-script.

---

## Editing notes

- Keep B-roll minimal. The dashboard is the star.
- When showing Arc explorer, blur or scroll past unrelated transactions
- Subtitle the spoken paragraph numbers ("Para 5.11", "Para 6.40-42") as
  on-screen text since they are critical to the narrative.
- Final 3 seconds: hold on the Para 5.11 marquee quote with the cursor at rest.
