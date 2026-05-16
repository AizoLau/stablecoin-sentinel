"""FastAPI backend for the Unhosted Wallet Risk Sentinel.

Endpoints
---------
GET  /health                   — liveness + audit count
GET  /decisions                — paginated history from audit_log (newest first)
GET  /events                   — Server-Sent Events stream of new decisions
POST /demo/trigger             — synthesize a transfer, run the full agent pipeline,
                                 record the audit row, publish to SSE subscribers

Run locally:
    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from web3 import Web3

from backend.agent.manager import ManagerAgent
from backend.chain.circle_wallets import CircleWalletsClient
from backend.chain.executor import CircleWalletsSigner, Executor
from backend.config import PROJECT_ROOT, Settings, get_settings
from backend.data.debank_client import DeBankClient
from backend.data.sanctions import SanctionsHit, SanctionsRegistry
from backend.rag.retrieve import HKMARetriever
from backend.store.audit_log import AuditLog
from backend.store.models import TransferEvent

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    settings: Settings
    debank: DeBankClient
    sanctions: SanctionsRegistry
    retriever: HKMARetriever
    manager: ManagerAgent
    circle: CircleWalletsClient
    executor: Executor
    audit: AuditLog
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    sub_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


state: AppState  # set in lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    global state
    load_dotenv()
    s = get_settings()

    debank = DeBankClient(s.debank_accesskey, s.debank_base_url)
    sanctions = SanctionsRegistry(s.sanctions_json_path)
    retriever = HKMARetriever(s)
    manager = ManagerAgent(s, debank, sanctions, retriever)
    circle = CircleWalletsClient(s.circle_api_key, s.circle_entity_secret)
    signer = CircleWalletsSigner(circle, s.circle_sentinel_wallet_id, s.mock_usdc_addr)
    executor = Executor(signer, s)
    audit = AuditLog(s.sqlite_path)

    state = AppState(
        settings=s,
        debank=debank,
        sanctions=sanctions,
        retriever=retriever,
        manager=manager,
        circle=circle,
        executor=executor,
        audit=audit,
    )
    logger.info("AppState initialized; %d HKMA chunks in RAG", retriever.collection_size())
    try:
        yield
    finally:
        await debank.close()
        await circle.close()


app = FastAPI(title="Unhosted Wallet Risk Sentinel", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the dashboard statically once it exists (M3-D).
_DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
if _DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=_DASHBOARD_DIR, html=True), name="dashboard")


# ----- Helpers -----


async def _broadcast(payload: dict) -> None:
    async with state.sub_lock:
        subs = list(state.subscribers)
    for q in subs:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("SSE subscriber queue full; dropping event")


def _unfreeze_target(target: str) -> dict:
    """OWNER-side unfreeze so the demo can be re-run cleanly."""
    s = state.settings
    w3 = Web3(Web3.HTTPProvider(s.arc_rpc_url))
    abi_path = PROJECT_ROOT / "backend" / "chain" / "abi" / "MockUSDC.json"
    abi = json.loads(abi_path.read_text(encoding="utf-8"))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(s.mock_usdc_addr), abi=abi
    )
    owner = w3.eth.account.from_key(s.deployer_private_key)
    target_cs = Web3.to_checksum_address(target)

    if not contract.functions.frozen(target_cs).call():
        return {"already_unfrozen": True}

    nonce = w3.eth.get_transaction_count(owner.address)
    tx = contract.functions.unfreezeAddress(target_cs).build_transaction(
        {"from": owner.address, "nonce": nonce, "gas": 80000}
    )
    signed = owner.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    return {
        "tx_hash": "0x" + tx_hash if not tx_hash.startswith("0x") else tx_hash,
        "block": receipt.blockNumber,
        "status": receipt.status,
    }


# ----- Schemas -----


class DemoTriggerBody(BaseModel):
    from_address: str | None = None
    to_address: str | None = None
    amount: int = Field(default=50_000_000, ge=1, description="raw units (6 decimals)")
    tx_hash: str | None = None
    tag_recipient: bool = Field(
        default=True, description="if true, inject the recipient into mock sanctions registry"
    )
    recipient_tags: list[str] = Field(default_factory=lambda: ["known-mixer", "sanctions-list"])
    unfreeze_first: bool = Field(default=False)


# ----- Endpoints -----


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "audit_count": state.audit.count(),
        "rag_collection_size": state.retriever.collection_size(),
        "sentinel_wallet": state.settings.circle_sentinel_wallet_address,
        "mock_usdc_addr": state.settings.mock_usdc_addr,
        "chain_id": state.settings.arc_chain_id,
    }


@app.get("/decisions")
async def decisions(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    return state.audit.list_recent(limit=limit, offset=offset)


@app.get("/events")
async def events(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)

    async def stream():
        async with state.sub_lock:
            state.subscribers.append(queue)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(
                        queue.get(), timeout=state.settings.sse_heartbeat_seconds
                    )
                    yield {"event": "decision", "data": json.dumps(payload)}
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": "{}"}
        finally:
            async with state.sub_lock:
                if queue in state.subscribers:
                    state.subscribers.remove(queue)

    return EventSourceResponse(stream())


@app.post("/demo/trigger")
async def demo_trigger(body: DemoTriggerBody) -> dict:
    s = state.settings
    from_addr = body.from_address or s.demo_alice_address
    to_addr = body.to_address or s.demo_bob_address
    if not from_addr or not to_addr:
        raise HTTPException(400, "from_address / to_address not configured")

    unfreeze_info = None
    if body.unfreeze_first:
        loop = asyncio.get_event_loop()
        unfreeze_info = await loop.run_in_executor(None, _unfreeze_target, to_addr)

    if body.tag_recipient:
        state.sanctions._index[to_addr.lower()] = SanctionsHit(
            address=to_addr.lower(),
            tags=tuple(body.recipient_tags),
            source="DEMO-OFAC-001",
            added="2026-05-16",
            paragraph_ref="7.5",
        )

    tx_hash = body.tx_hash or ("0x" + os.urandom(32).hex())
    transfer = TransferEvent(
        tx_hash=tx_hash,
        block_number=0,
        log_index=0,
        from_address=from_addr,
        to_address=to_addr,
        amount=body.amount,
    )

    decision, retrieved = await state.manager.decide(transfer)
    receipt = await state.executor.execute(decision)
    record_id = state.audit.append(transfer, decision, receipt, retrieved=retrieved)

    record = state.audit.list_recent(limit=1)[0]
    await _broadcast({"type": "decision", "record": record})

    return {
        "record_id": record_id,
        "unfreeze": unfreeze_info,
        "decision": {
            "action": decision.action.value,
            "target": decision.target_address,
            "risk_score": decision.risk_score,
            "paragraphs": decision.paragraphs_cited,
        },
        "receipt": {
            "status": receipt.status,
            "tx_hash": receipt.tx_hash,
            "error": receipt.error,
            "explorer": f"{s.arc_explorer_url}/tx/{receipt.tx_hash}" if receipt.tx_hash else None,
        },
    }
