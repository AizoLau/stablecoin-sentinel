# REST API Reference

Base URL: `http://127.0.0.1:8000` (local) or `https://<your-service>.onrender.com` (deployed).

All endpoints return JSON. Errors use HTTP standard status codes; the response
body is `{"detail": "<message>"}` on 4xx/5xx.

## Endpoints at a glance

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + RAG/audit/sentinel-balance probe |
| GET | `/decisions` | Paginated audit-log history (newest first) |
| GET | `/events` | Server-Sent Events stream of new decisions |
| POST | `/demo/trigger` | Synthesize a transfer, run agent pipeline, submit on-chain |
| GET | `/dashboard/` | Static dashboard UI (vanilla HTML/JS) |

---

## GET `/health`

Liveness + readiness probe. Used by Render/Railway health checks and the
dashboard status dot.

### Request

No parameters.

### Response 200

```json
{
  "ok": true,
  "audit_count": 42,
  "rag_collection_size": 408,
  "sentinel_wallet": "0x11afacf004f144db1df3857ee1ea555d233c33c7",
  "sentinel_balance_wei": 19985384866900243244,
  "sentinel_gas_low": false,
  "mock_usdc_addr": "0xA43143DF2C00Bce848af35eF4Cb69911Ae37d95B",
  "chain_id": 5042002
}
```

### Field semantics

| Field | Meaning |
|---|---|
| `ok` | `true` iff `sentinel_gas_low` is `false`. Drives the dashboard status dot color. |
| `audit_count` | Total rows in `audit_records` table. |
| `rag_collection_size` | Number of chunks in Chroma collection `hkma_aml_guideline` (expect 408 = 149 HKMA + 259 Cap 656). |
| `sentinel_wallet` | Address of the Circle Wallet that signs enforcement txs. |
| `sentinel_balance_wei` | Native gas balance on Arc. Arc gas is USDC-denominated but the RPC returns 18-decimal `wei`. `1 USDC == 1e18`. |
| `sentinel_gas_low` | `true` if balance < 1 USDC. |
| `mock_usdc_addr` | Deployed contract address. |
| `chain_id` | 5042002 for Arc Testnet. |

### curl example

```powershell
curl https://<host>/health
```

---

## GET `/decisions`

Returns audit-log rows, newest first.

### Query parameters

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int (1–200) | 50 | Maximum rows to return. |
| `offset` | int (≥0) | 0 | Skip the first N rows (for pagination). |

### Response 200

Array of audit records. Each record:

```json
{
  "id": 12,
  "created_at": "2026-05-16T15:42:08.221034+00:00",
  "tx_hash": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "block_number": 0,
  "from_address": "0x6F106e2D89B58FEC6Fa1037Fd6e2cEAa586F7d59",
  "to_address": "0x0F7Ba243461ba7E5043383E9D4D9B96AE8b02201",
  "amount": 50000000,
  "action": "freeze",
  "target_address": "0x0F7Ba243461ba7E5043383E9D4D9B96AE8b02201",
  "risk_score": 95,
  "paragraphs_cited": ["5.10", "6.29", "4.39"],
  "retrieved_paragraphs": [
    {
      "paragraph_id": "5.10",
      "document": "HKMA-AML-Guideline-2025-08",
      "text": "5.10. All on-chain stablecoin transactions are recorded ...",
      "similarity": 0.7457
    },
    "... 7 more chunks ..."
  ],
  "reasoning_md": "The licensee has frozen the recipient address ...",
  "execution_status": "confirmed",
  "execution_tx_hash": "0xee780d8c02fdea8fb225e3b14a1c1e7bc614b5a030c7cf43c4893c0cbb91b066",
  "execution_error": null
}
```

### Field semantics

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Auto-increment primary key. |
| `created_at` | ISO 8601 UTC | When the decision was recorded. |
| `tx_hash` | `0x`-prefixed hex | Origin transfer's tx hash (synthesized for demo scenarios). |
| `block_number` | int | 0 for synthesized transfers; real block for chain-listened transfers. |
| `from_address`, `to_address`, `amount` | — | Transfer details. `amount` is raw units, 6 decimals. |
| `action` | `"pass" \| "refund" \| "quarantine" \| "freeze"` | Compliance Decider's chosen action. |
| `target_address` | hex | Address the action operates on. Empty for `pass`. |
| `risk_score` | 0–100 int | Final risk score from Compliance Decider (may differ from Risk Assessor's). |
| `paragraphs_cited` | string[] | HKMA Para IDs (no prefix, e.g. `["5.10", "6.29"]`). MUST be a subset of `retrieved_paragraphs[].paragraph_id`. |
| `retrieved_paragraphs` | object[] | The full top-K RAG retrieval pool (8 by default). Used by dashboard to render evidence. |
| `reasoning_md` | string | Reporter's markdown justification (Para 5.7). Starts with `[FALLBACK ...]` if LLM pipeline failed. |
| `execution_status` | `"confirmed" \| "failed" \| "skipped"` | On-chain action outcome. `skipped` for `pass`. |
| `execution_tx_hash` | hex or null | Arc tx hash. Null for `pass` or failures with no tx submitted. |
| `execution_error` | string or null | Truncated error message from Circle Wallets or executor. |

### curl example

```powershell
curl "https://<host>/decisions?limit=10&offset=0"
```

---

## GET `/events`

Server-Sent Events stream. Each new audit row is pushed as an `event: decision`
frame. Heartbeats (`event: heartbeat`) fire every `SSE_HEARTBEAT_SECONDS`
(default 15).

### Headers

`Accept: text/event-stream` required by SSE clients (most browsers' EventSource
sets it automatically).

### Stream frames

```
event: heartbeat
data: {}

event: decision
data: {"type": "decision", "record": { ... same shape as /decisions entry ... }}
```

### JavaScript client example

```js
const es = new EventSource("https://<host>/events");
es.addEventListener("decision", (ev) => {
  const payload = JSON.parse(ev.data);
  console.log("new decision", payload.record);
});
es.addEventListener("heartbeat", () => console.log("alive"));
es.onerror = () => console.error("SSE error");
```

### Notes

- The connection stays open indefinitely. Per-client queues are capped at 64
  events; full queues drop events with a warning log.
- Render's free plan kills idle connections after ~5 minutes — heartbeats
  every 15 s keep it alive.

---

## POST `/demo/trigger`

Synthesize a transfer, run the full agent pipeline, optionally unfreeze the
recipient first, submit the resulting action on-chain via Circle Wallets,
record an audit row, broadcast to SSE subscribers.

### Request body

```json
{
  "scenario": "sanctioned_recipient",
  "from_address": null,
  "to_address": null,
  "amount": 50000000,
  "tx_hash": null,
  "unfreeze_first": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `scenario` | enum | `"sanctioned_recipient"` | One of: `sanctioned_recipient`, `cctp_inflow_ethereum`, `clean_pass`. Controls which sanctions tags get injected. |
| `from_address` | string \| null | `$DEMO_ALICE_ADDRESS` | Override sender. Default reads from env. |
| `to_address` | string \| null | `$DEMO_BOB_ADDRESS` | Override recipient. |
| `amount` | int ≥1 | 50,000,000 | Raw units (6 decimals). `50e6` = 50 mUSDC. |
| `tx_hash` | string \| null | random | Synthesized tx hash for the synthesized TransferEvent. Auto-generated if omitted. |
| `unfreeze_first` | bool | `false` | If `true`, OWNER calls `MockUSDC.unfreezeAddress(to_address)` before the pipeline runs. Required for replaying the same FREEZE scenario. |

### Scenario behavior

| `scenario` | Injected sanctions tags | Expected action |
|---|---|---|
| `sanctioned_recipient` | `("known-mixer", "sanctions-list")`, paragraph_ref `7.5` | FREEZE |
| `cctp_inflow_ethereum` | `("cross-chain-cctp-inflow-from-ethereum", "tornado-cash-relay-history", "cross-border-designated-party")`, paragraph_ref `6.41` | FREEZE (cites cross-border paragraphs) |
| `clean_pass` | Recipient is removed from sanctions registry | PASS |

### Response 200

```json
{
  "record_id": 12,
  "scenario": "sanctioned_recipient",
  "cctp": null,
  "unfreeze": {"tx_hash": "0xa123...", "block": 42457743, "status": 1},
  "decision": {
    "action": "freeze",
    "target": "0x0F7Ba243461ba7E5043383E9D4D9B96AE8b02201",
    "risk_score": 95,
    "paragraphs": ["5.10", "6.29", "4.39"]
  },
  "receipt": {
    "status": "confirmed",
    "tx_hash": "0xee780d8c02fdea8fb225e3b14a1c1e7bc614b5a030c7cf43c4893c0cbb91b066",
    "error": null,
    "explorer": "https://explorer.testnet.arc.network/tx/0xee780d8c02fdea8fb225e3b14a1c1e7bc614b5a030c7cf43c4893c0cbb91b066"
  }
}
```

| Field | Meaning |
|---|---|
| `record_id` | The id of the audit row written. |
| `scenario` | Echo of the input scenario. |
| `cctp` | Non-null only for `cctp_inflow_ethereum`. Contains `{source_chain, source_domain, source_tx_hash, risk_tags}`. |
| `unfreeze` | Non-null only if `unfreeze_first: true` and the address was actually frozen. |
| `decision` | Summary of the agent's output. |
| `receipt` | Summary of the on-chain execution. `explorer` is a direct link. |

### Error responses

| Status | Cause | Resolution |
|---|---|---|
| 400 | Unknown `scenario` value | Use one of the three documented enums. |
| 400 | `from_address` or `to_address` not configured | Set the env vars or pass them in the body. |
| 500 | LLM + sanctions both failed | The rule-engine fallback should prevent this; check `execution_error` in `/decisions`. |

### Pipeline timing

End-to-end ~20–25 seconds:

- Risk Assessor (Gemini flash): ~3 s
- Compliance Decider (Gemini pro): ~5 s
- Reporter (Gemini pro): ~5 s
- Circle Wallets contract execution + Arc confirmation: ~7 s
- DeBank + Chroma retrieval + auxiliary: ~2 s

### curl example

```powershell
curl -X POST "https://<host>/demo/trigger" `
  -H "Content-Type: application/json" `
  -d '{"scenario":"cctp_inflow_ethereum","unfreeze_first":true}'
```

---

## GET `/dashboard/*`

Static file mount. Serves the vanilla HTML/JS dashboard from the `dashboard/`
directory. No API surface here — just files. The dashboard talks to the four
endpoints above.

| Path | File |
|---|---|
| `/dashboard/` | `dashboard/index.html` |
| `/dashboard/app.js` | `dashboard/app.js` |
| `/dashboard/style.css` | `dashboard/style.css` |

---

## Concurrency model

- All endpoints are async and share a single in-process `AppState`.
- `DeBankClient` and `CircleWalletsClient` each hold one `httpx.AsyncClient`
  with connection pooling — safe across concurrent requests.
- The `SanctionsRegistry` is in-memory and is intentionally mutated by demo
  scenarios. **Do not run two scenarios in parallel against the same backend
  instance** if you care about deterministic sanctions tags — they race.
- `SQLite` audit log uses `sqlmodel` default connection pool; concurrent
  inserts are fine (auto-id allocation is locked).
- SSE subscribers list is protected by `state.sub_lock`.

## Rate-limit considerations

- **Gemini API**: free tier ~60 RPM, ~100k TPM per project. Each `/demo/trigger`
  spends ~4 Gemini calls (1 embedding + 3 generations). You'll hit RPM ceilings
  at ~15 triggers/minute.
- **Circle Wallets**: not documented publicly; we've seen no issues at <10 contract
  executions per minute.
- **DeBank Cloud Pro**: paid tier rate-limit depends on your plan; check
  `cloud.debank.com`.
- **Arc Testnet RPC**: free, generous; the listener and executor do bounded
  retries (`tenacity`).
