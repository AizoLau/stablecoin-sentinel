"""M2 end-to-end demo: Transfer -> Agent decision -> On-chain enforcement.

Repeatable CLI script that wraps the full M2 verification gate. Use
``--unfreeze-first`` to reset Bob's frozen state before running (so the demo
can be replayed during video recording).

Run from project root:
    python -m backend.cli.m2_demo
    python -m backend.cli.m2_demo --unfreeze-first
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

from backend.agent.manager import ManagerAgent
from backend.chain.circle_wallets import CircleWalletsClient
from backend.chain.executor import CircleWalletsSigner, Executor
from backend.config import PROJECT_ROOT, get_settings
from backend.data.debank_client import DeBankClient
from backend.data.sanctions import SanctionsHit, SanctionsRegistry
from backend.rag.retrieve import HKMARetriever
from backend.store.models import TransferEvent


ABI_PATH = PROJECT_ROOT / "backend" / "chain" / "abi" / "MockUSDC.json"


def banner(msg: str) -> None:
    print("\n" + "=" * 70)
    print(msg)
    print("=" * 70)


async def unfreeze(settings, target: str) -> None:
    """Owner-side unfreeze so the demo can be re-run cleanly."""
    w3 = Web3(Web3.HTTPProvider(settings.arc_rpc_url))
    abi = json.loads(ABI_PATH.read_text(encoding="utf-8"))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(settings.mock_usdc_addr), abi=abi
    )
    owner = w3.eth.account.from_key(settings.deployer_private_key)
    target_cs = Web3.to_checksum_address(target)

    if not contract.functions.frozen(target_cs).call():
        print(f"  {target} already unfrozen; skipping.")
        return

    nonce = w3.eth.get_transaction_count(owner.address)
    tx = contract.functions.unfreezeAddress(target_cs).build_transaction(
        {"from": owner.address, "nonce": nonce, "gas": 60000}
    )
    signed = owner.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    print(f"  unfreeze tx submitted: 0x{tx_hash}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    print(f"  unfreeze confirmed in block {receipt.blockNumber}, status={receipt.status}")


async def run_demo(args: argparse.Namespace) -> int:
    load_dotenv()
    s = get_settings()

    alice = s.demo_alice_address
    bob = s.demo_bob_address

    if not all([alice, bob, s.mock_usdc_addr, s.circle_api_key, s.gemini_api_key, s.debank_accesskey]):
        print("Missing required env variables (.env). Check ALICE / BOB / MOCK_USDC_ADDR / CIRCLE / GEMINI / DEBANK keys.")
        return 1

    if args.unfreeze_first:
        banner(f"PRE-STEP: Unfreezing {bob} (OWNER action)")
        await unfreeze(s, bob)

    banner("STEP 1: Inject Bob into mock sanctions registry (simulates OFAC tagging)")
    sanctions = SanctionsRegistry(s.sanctions_json_path)
    sanctions._index[bob.lower()] = SanctionsHit(
        address=bob.lower(),
        tags=("known-mixer", "sanctions-list"),
        source="DEMO-OFAC-001",
        added="2026-05-16",
        paragraph_ref="7.5",
    )
    print(f"  Bob tagged: known-mixer, sanctions-list (source DEMO-OFAC-001).")

    banner("STEP 2: Synthesize TransferEvent Alice -> Bob 50 mUSDC")
    event = TransferEvent(
        tx_hash="0x" + "aa" * 32,
        block_number=0,
        log_index=0,
        from_address=alice,
        to_address=bob,
        amount=50_000_000,
    )
    print(f"  from:   {event.from_address}")
    print(f"  to:     {event.to_address}")
    print(f"  amount: {event.amount / 1e6:.2f} mUSDC")

    banner("STEP 3: ManagerAgent decides (Gemini + DeBank + Sanctions + RAG)")
    debank = DeBankClient(s.debank_accesskey, s.debank_base_url)
    retriever = HKMARetriever(s)
    manager = ManagerAgent(s, debank, sanctions, retriever)
    try:
        decision = await manager.decide(event)
    finally:
        await debank.close()
    print(f"  action:      {decision.action.value.upper()}")
    print(f"  target:      {decision.target_address}")
    print(f"  risk_score:  {decision.risk_score}")
    print(f"  paragraphs:  {decision.paragraphs_cited}")
    print(f"\n  Reasoning (excerpt):\n    {decision.reasoning_md[:400]}...")

    banner("STEP 4: Executor submits via Circle Wallets API (MPC sign)")
    circle = CircleWalletsClient(s.circle_api_key, s.circle_entity_secret)
    signer = CircleWalletsSigner(circle, s.circle_sentinel_wallet_id, s.mock_usdc_addr)
    executor = Executor(signer, s)
    try:
        receipt = await executor.execute(decision)
    finally:
        await circle.close()
    print(f"  status:           {receipt.status}")
    print(f"  on-chain tx hash: {receipt.tx_hash}")
    if receipt.error:
        print(f"  error:            {receipt.error}")
        return 2

    banner("STEP 5: Verify on-chain state")
    w3 = Web3(Web3.HTTPProvider(s.arc_rpc_url))
    abi = json.loads(ABI_PATH.read_text(encoding="utf-8"))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(s.mock_usdc_addr), abi=abi
    )
    bob_frozen = contract.functions.frozen(Web3.to_checksum_address(bob)).call()
    bob_reason = contract.functions.freezeReason(Web3.to_checksum_address(bob)).call()
    print(f"  Bob.frozen():        {bob_frozen}")
    print(f"  Bob.freezeReason():  {bob_reason!r}")
    explorer = f"{s.arc_explorer_url}/tx/{receipt.tx_hash}"
    print(f"\n  Arc explorer:        {explorer}")

    if not bob_frozen:
        print("\n  FAIL: Bob is not frozen.")
        return 3

    banner("M2 demo complete.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="M2 end-to-end demo")
    parser.add_argument(
        "--unfreeze-first",
        action="store_true",
        help="Unfreeze Bob via OWNER before running (allows replay).",
    )
    args = parser.parse_args()
    rc = asyncio.run(run_demo(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
