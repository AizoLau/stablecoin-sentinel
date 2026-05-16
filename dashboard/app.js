// Dashboard logic — vanilla JS (no build step).
// Talks to the FastAPI backend at the same origin: /health, /decisions, /events, /demo/trigger.

const API = window.location.origin;
const EXPLORER_BASE = "https://explorer.testnet.arc.network/tx/";

const state = {
  records: [],     // newest first
  selectedId: null,
  eventSource: null,
};

// ---- Element refs ----
const els = {
  sseDot:        document.getElementById("sse-dot"),
  chain:         document.getElementById("status-chain"),
  sentinel:      document.getElementById("status-sentinel"),
  count:         document.getElementById("status-count"),
  trigger:       document.getElementById("btn-trigger"),
  refresh:       document.getElementById("btn-refresh"),
  unfreezeOpt:   document.getElementById("opt-unfreeze"),
  feedEmpty:     document.getElementById("feed-empty"),
  feedList:      document.getElementById("feed-list"),
  detailPane:    document.getElementById("detail-pane"),
};

// ---- Helpers ----
const shortAddr = (a) => a ? `${a.slice(0, 6)}…${a.slice(-4)}` : "";
const shortHash = (h) => h ? `${h.slice(0, 10)}…${h.slice(-6)}` : "";
const fmtTime = (iso) => {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return d.toLocaleDateString();
};
const escapeHtml = (s) =>
  (s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));

// ---- Data fetch ----
async function loadHealth() {
  const r = await fetch(`${API}/health`);
  const data = await r.json();
  els.chain.textContent = String(data.chain_id);
  els.sentinel.textContent = shortAddr(data.sentinel_wallet);
  els.count.textContent = String(data.audit_count);
}

async function loadDecisions() {
  const r = await fetch(`${API}/decisions?limit=50`);
  const data = await r.json();
  state.records = data;
  renderFeed();
  if (state.records.length && !state.selectedId) {
    selectRecord(state.records[0].id);
  }
}

async function triggerDemo() {
  els.trigger.disabled = true;
  els.trigger.textContent = "Submitting on-chain action…";
  try {
    const r = await fetch(`${API}/demo/trigger`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        unfreeze_first: els.unfreezeOpt.checked,
        tag_recipient: true,
      }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  } catch (err) {
    alert(`Demo trigger failed: ${err.message}`);
  } finally {
    els.trigger.disabled = false;
    els.trigger.textContent = "Trigger demo transfer (Alice → Bob, sanctioned)";
  }
}

// ---- Render ----
function renderFeed() {
  if (!state.records.length) {
    els.feedEmpty.style.display = "block";
    els.feedList.innerHTML = "";
    return;
  }
  els.feedEmpty.style.display = "none";
  els.feedList.innerHTML = state.records.map((rec) => {
    const cls = state.selectedId === rec.id ? "selected" : "";
    return `
      <li class="${cls}" data-id="${rec.id}">
        <div class="row1">
          <span class="action-badge action-${rec.action}">${rec.action}</span>
          <span class="id">#${rec.id} · ${fmtTime(rec.created_at)}</span>
        </div>
        <div class="addr">${shortAddr(rec.from_address)} → ${shortAddr(rec.to_address)} · ${(rec.amount / 1e6).toFixed(2)} mUSDC</div>
      </li>
    `;
  }).join("");
  for (const li of els.feedList.querySelectorAll("li")) {
    li.addEventListener("click", () => selectRecord(parseInt(li.dataset.id, 10)));
  }
}

function selectRecord(id) {
  state.selectedId = id;
  renderFeed();
  const rec = state.records.find((r) => r.id === id);
  if (!rec) return;

  const scoreBucket = rec.risk_score >= 70 ? "high" : rec.risk_score >= 30 ? "mid" : "low";
  const execStatusClass = `status-${rec.execution_status || "skipped"}`;
  const execTxLink = rec.execution_tx_hash
    ? `<a href="${EXPLORER_BASE}${rec.execution_tx_hash}" target="_blank" rel="noopener">${shortHash(rec.execution_tx_hash)} ↗</a>`
    : "—";

  els.detailPane.innerHTML = `
    <h2>
      <span class="action-badge action-${rec.action}">${rec.action}</span>
      Decision #${rec.id}
      <span style="color:var(--muted); font-size:12px; font-weight:normal; margin-left:auto">${fmtTime(rec.created_at)}</span>
    </h2>

    <dl class="meta">
      <dt>Transfer</dt>
      <dd><code>${escapeHtml(rec.from_address)}</code> → <code>${escapeHtml(rec.to_address)}</code></dd>
      <dt>Amount</dt>
      <dd>${(rec.amount / 1e6).toFixed(2)} mUSDC <span style="color:var(--muted)">(${rec.amount} raw)</span></dd>
      <dt>Tx hash</dt>
      <dd><code>${escapeHtml(rec.tx_hash)}</code></dd>
      <dt>Target</dt>
      <dd><code>${escapeHtml(rec.target_address) || "—"}</code></dd>
    </dl>

    <div class="section-title">Risk score</div>
    <div class="score-bar ${scoreBucket}">
      <div class="track"><div class="fill" style="width:${rec.risk_score}%"></div></div>
      <span class="mono">${rec.risk_score} / 100</span>
    </div>

    <div class="section-title">HKMA paragraphs cited (retrieved, not hallucinated)</div>
    <div class="paragraphs">
      ${rec.paragraphs_cited.map((p) => `<span class="paragraph-chip">Para ${escapeHtml(p)}</span>`).join("") || "<span class='empty'>(none)</span>"}
    </div>

    <div class="section-title">Agent reasoning</div>
    <div class="reasoning">${escapeHtml(rec.reasoning_md)}</div>

    <div class="section-title">On-chain execution</div>
    <div class="execution">
      <div>Status: <strong class="${execStatusClass}">${escapeHtml(rec.execution_status)}</strong></div>
      <div>Tx: ${execTxLink}</div>
      ${rec.execution_error ? `<div style="color:var(--freeze); margin-top:6px">Error: ${escapeHtml(rec.execution_error)}</div>` : ""}
    </div>
  `;
}

function setSseStatus(live) {
  els.sseDot.classList.toggle("live", !!live);
  els.sseDot.classList.toggle("stale", !live);
}

function connectSse() {
  if (state.eventSource) state.eventSource.close();
  const es = new EventSource(`${API}/events`);
  state.eventSource = es;

  es.addEventListener("open",      () => setSseStatus(true));
  es.addEventListener("error",     () => setSseStatus(false));
  es.addEventListener("heartbeat", () => setSseStatus(true));
  es.addEventListener("decision", (ev) => {
    setSseStatus(true);
    try {
      const payload = JSON.parse(ev.data);
      const rec = payload?.record;
      if (!rec) return;
      // upsert by id, newest first
      state.records = [rec, ...state.records.filter((r) => r.id !== rec.id)];
      els.count.textContent = String(state.records.length);
      renderFeed();
      if (!state.selectedId) selectRecord(rec.id);
    } catch (e) {
      console.error("bad SSE payload", e);
    }
  });
}

// ---- Boot ----
async function init() {
  await loadHealth();
  await loadDecisions();
  connectSse();
  els.trigger.addEventListener("click", triggerDemo);
  els.refresh.addEventListener("click", () => { loadHealth(); loadDecisions(); });
}

init().catch((err) => {
  console.error(err);
  els.detailPane.innerHTML = `<div class="empty large">Failed to load: ${escapeHtml(err.message)}</div>`;
});
