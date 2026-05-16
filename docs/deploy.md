# Deployment Guide

How to take this repo from "works on my laptop" to a public demo URL the
HK Stablecoin Challenge judges can open.

Two paths, listed easy → most-control:

1. [Render Blueprint (recommended, free)](#path-1-render-blueprint-recommended)
2. [Railway (also fine, $5/mo trial)](#path-2-railway)
3. [Self-host on a VPS (max control)](#path-3-self-host)

All paths assume you have:

- A GitHub account
- The repo pushed to a GitHub remote (private is fine — Render and Railway both connect via OAuth)
- The seven secrets ready in your `.env` (you have these from M2)

---

## Path 1: Render Blueprint (recommended)

Render's free tier is enough for the hackathon demo. Build time 4-6 minutes,
deploy 1-2 minutes. The instance **sleeps after 15 minutes idle**; first
request after sleep takes ~30 seconds to wake.

### Step 1 — Push the repo to GitHub

```powershell
cd C:\Users\Administrator\Desktop\StablecoinChallenge
git remote add origin git@github.com:<your-username>/stablecoin-sentinel.git
git push -u origin master
```

If your `master` branch is called `main`, adjust the `branch:` field in
`render.yaml` accordingly.

### Step 2 — Create a Render account + connect GitHub

1. Sign up at https://render.com (use the same email as your Circle Developer
   Account if you want submission consistency — not required).
2. Settings → Connect GitHub. Authorize the repo.

### Step 3 — One-click deploy

1. Render dashboard → **New** → **Blueprint**.
2. Pick your repo. Render auto-detects `render.yaml` at the root.
3. You'll see a form listing seven `sync: false` secrets that need values:
   - `GEMINI_API_KEY`
   - `DEBANK_ACCESSKEY`
   - `CIRCLE_API_KEY`
   - `CIRCLE_ENTITY_SECRET`
   - `CIRCLE_SENTINEL_WALLET_ID`
   - `CIRCLE_SENTINEL_WALLET_ADDRESS`
   - `DEPLOYER_PRIVATE_KEY`

   Copy these from your local `.env`. Submit.

4. Render starts the Docker build. Watch the logs tab.

### Step 4 — Wait for green and verify

When the service status flips to **Live**:

```powershell
# Health probe from any client
curl https://<your-service>.onrender.com/health

# Should return:
# {"ok": true, "audit_count": 0, "rag_collection_size": 408, ...}
```

Open the dashboard:

```
https://<your-service>.onrender.com/dashboard/
```

### Step 5 — Pre-warm before recording

Render free plan sleeps after 15 minutes. Before pressing Record on your demo
video, hit `/health` once to wake it up:

```powershell
curl https://<your-service>.onrender.com/health
# Wait until you see the JSON come back (30-40s on cold start).
# Now you have ~15 minutes of warm response time. Plenty for a 3-minute demo.
```

### Common Render gotchas

| Symptom | Cause | Fix |
|---|---|---|
| Build fails on `pip install -e .` | Memory limit on free plan | Trim deps; `chromadb` is heavy. Last resort: upgrade to $7 starter |
| Health check fails after build OK | RPC call to Arc in `/health` is slow | Render gives 5 minutes for first health check; if you don't pass, refresh deploy logs |
| `chroma_db` not found at runtime | Was excluded by `.dockerignore` | Check that `.dockerignore` does **not** list `chroma_db/`; ours doesn't |
| 502 Bad Gateway on the URL | Service is sleeping | Hit `/health` once, wait 30s |

---

## Path 2: Railway

Railway has no sleep on the trial plan. ~$5 free credit lasts the hackathon and a few weeks beyond.

```powershell
# Install Railway CLI (one-time)
npm install -g @railway/cli
railway login
railway init   # links the repo to a new Railway project
```

Railway auto-detects `Dockerfile`. Add the same seven secrets via:

```powershell
railway variables set GEMINI_API_KEY=<your-key>
# ... repeat for each
```

Or paste them into the web UI under Variables.

```powershell
railway up   # builds + deploys
```

Get the URL:

```powershell
railway domain   # or check the Railway dashboard
```

Test:

```
https://<service>.up.railway.app/health
https://<service>.up.railway.app/dashboard/
```

---

## Path 3: Self-host

If you have a VPS (DigitalOcean, Hetzner, AWS EC2):

```bash
# On the VPS
git clone <your-repo>
cd stablecoin-sentinel
docker build -t sentinel:latest .

# Write .env on the server with the seven secrets + the committed-public vars
docker run -d --name sentinel \
  --env-file .env \
  -p 8000:8000 \
  --restart=unless-stopped \
  sentinel:latest

# Front with Caddy / Nginx for TLS termination
```

Caddyfile (minimal):

```caddy
sentinel.example.com {
    reverse_proxy localhost:8000
}
```

`systemctl reload caddy` and you're live.

---

## Post-deploy sanity tests

Run these against the public URL **before** recording the video.

```powershell
# 1. Health
curl https://<host>/health
# Expect: {"ok": true, "rag_collection_size": 408, ...}

# 2. RAG retrieval still works in production
# (no curl-able endpoint; verify via the next two)

# 3. Each demo scenario produces an audit row + a real on-chain tx
curl -X POST https://<host>/demo/trigger \
  -H "Content-Type: application/json" \
  -d '{"scenario": "sanctioned_recipient", "unfreeze_first": true}'
# Expect: {"record_id": N, "decision": {...}, "receipt": {"tx_hash": "0x...", ...}}

# 4. The tx is verifiable on Arc explorer
# Open the explorer URL returned in the response
```

If all four pass, you're shippable.

---

## What can go wrong in production

| Risk | Likelihood | Mitigation already in repo |
|---|---|---|
| Render goes to sleep mid-demo | Medium (first 30s after a 15-min idle) | Pre-warm with `/health` before recording. Or upgrade to $7 starter. |
| Sentinel wallet runs out of gas | Low (started with 20 USDC, each freeze ~0.0002 USDC) | `/health` flags `sentinel_gas_low: true` when balance < 1 USDC. Top up via faucet. |
| Gemini API hits rate limit | Low on demo traffic; Medium if judges hammer it | Rule-engine fallback in `backend/agent/manager.py` writes a FREEZE audit row even when Gemini is fully down. |
| Circle Wallets API outage | Very low | Audit row records `execution_error`; user-visible "failed" status in the dashboard. Decision is not lost. |
| Arc Testnet RPC flake | Low–Medium | Listener uses tenacity retry; for the demo we don't need the listener (we use `/demo/trigger`). |
| Bob already frozen from a previous demo | Certain on the second run | `unfreeze_first: true` in the trigger payload handles this; dashboard button has the checkbox ticked by default. |

---

## Last-mile checklist before Ignyte submission

- [ ] Public demo URL works (open in incognito to verify no logged-in state)
- [ ] `/dashboard/` loads, status dot is green, all three scenario buttons clickable
- [ ] Triggering "Sanctioned recipient" produces a freeze tx visible on Arc explorer
- [ ] Triggering "Clean transfer" produces a PASS, no on-chain tx
- [ ] README.md renders correctly on GitHub
- [ ] TRACEABILITY.md and ARCHITECTURE.md are linked from README
- [ ] docs/circle_product_feedback.md exists with non-empty content
- [ ] Video is recorded, < 4 minutes, uploaded to Loom / YouTube unlisted
- [ ] Submitted on Ignyte with all nine required fields
