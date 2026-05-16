"""Sentinel action executor.

Bridges agent decisions (Decision model) to on-chain enforcement calls on MockUSDC.
Abstracts the signing backend behind a Protocol so we can swap between Circle Wallets
(production, MPC-backed) and local keystore (fallback / unit test) without changing
caller code. M2 demo path: CircleWalletsSigner.
"""

from __future__ import annotations

import logging
from typing import Protocol

from backend.chain.circle_wallets import CircleWalletsClient
from backend.config import Settings
from backend.store.models import Action, Decision, ExecutionReceipt

logger = logging.getLogger(__name__)


# Solidity ABI function signatures — must match MockUSDC.sol exactly.
SIG_FREEZE = "freezeAddress(address,string,string)"
SIG_REFUND = "refundTransfer(bytes32,address,address,uint256,string)"
SIG_QUARANTINE = "quarantineTransfer(bytes32,address,address,uint256,string)"


class TxSigner(Protocol):
    """Interface implemented by Circle / local-keystore signing backends."""

    async def freeze_address(
        self, target: str, reason: str, paragraph_ref: str
    ) -> ExecutionReceipt: ...

    async def refund_transfer(
        self,
        original_tx_hash: str,
        from_addr: str,
        to_addr: str,
        amount: int,
        paragraph_ref: str,
    ) -> ExecutionReceipt: ...

    async def quarantine_transfer(
        self,
        original_tx_hash: str,
        from_addr: str,
        recovery: str,
        amount: int,
        paragraph_ref: str,
    ) -> ExecutionReceipt: ...


class CircleWalletsSigner:
    """Signs and submits MockUSDC calls via Circle Wallets API."""

    def __init__(
        self,
        circle: CircleWalletsClient,
        wallet_id: str,
        contract_address: str,
    ):
        self.circle = circle
        self.wallet_id = wallet_id
        self.contract = contract_address

    async def _execute(
        self, signature: str, params: list, label: str
    ) -> ExecutionReceipt:
        logger.info("Circle submit: %s params=%s", label, params)
        try:
            tx_id = await self.circle.submit_contract_execution(
                wallet_id=self.wallet_id,
                contract_address=self.contract,
                abi_function_signature=signature,
                abi_parameters=params,
            )
        except Exception as exc:
            logger.exception("Circle submit failed: %s", label)
            return ExecutionReceipt(tx_hash=None, status="failed", error=str(exc))

        result = await self.circle.wait_for_confirmation(tx_id)
        status = "confirmed" if result.state in {"CONFIRMED", "COMPLETE"} else "failed"
        return ExecutionReceipt(
            tx_hash=result.on_chain_tx_hash,
            status=status,
            error=result.error,
        )

    async def freeze_address(
        self, target: str, reason: str, paragraph_ref: str
    ) -> ExecutionReceipt:
        return await self._execute(
            SIG_FREEZE, [target, reason, paragraph_ref], "freeze"
        )

    async def refund_transfer(
        self,
        original_tx_hash: str,
        from_addr: str,
        to_addr: str,
        amount: int,
        paragraph_ref: str,
    ) -> ExecutionReceipt:
        # bytes32 wants 0x-prefixed 32-byte hex; pad if necessary
        tx_hex = original_tx_hash if original_tx_hash.startswith("0x") else f"0x{original_tx_hash}"
        return await self._execute(
            SIG_REFUND,
            [tx_hex, from_addr, to_addr, str(amount), paragraph_ref],
            "refund",
        )

    async def quarantine_transfer(
        self,
        original_tx_hash: str,
        from_addr: str,
        recovery: str,
        amount: int,
        paragraph_ref: str,
    ) -> ExecutionReceipt:
        tx_hex = original_tx_hash if original_tx_hash.startswith("0x") else f"0x{original_tx_hash}"
        return await self._execute(
            SIG_QUARANTINE,
            [tx_hex, from_addr, recovery, str(amount), paragraph_ref],
            "quarantine",
        )


class Executor:
    """Dispatches Decision.action to the appropriate signer method.

    The signer is injected — for M2 we use CircleWalletsSigner; tests use a
    fake signer that records calls without hitting the network.
    """

    def __init__(self, signer: TxSigner, settings: Settings):
        self.signer = signer
        self.settings = settings

    async def execute(self, decision: Decision) -> ExecutionReceipt:
        action = decision.action
        paragraph_ref = ", ".join(decision.paragraphs_cited) or "5.10(c)"
        transfer = decision.transfer

        if action == Action.PASS:
            return ExecutionReceipt(tx_hash=None, status="skipped")

        if action == Action.FREEZE:
            return await self.signer.freeze_address(
                target=decision.target_address,
                reason=f"risk_score={decision.risk_score}",
                paragraph_ref=paragraph_ref,
            )

        if action == Action.REFUND:
            return await self.signer.refund_transfer(
                original_tx_hash=transfer.tx_hash,
                from_addr=transfer.from_address,
                to_addr=transfer.to_address,
                amount=transfer.amount,
                paragraph_ref=paragraph_ref,
            )

        if action == Action.QUARANTINE:
            recovery = self.settings.demo_recovery_address
            if not recovery:
                return ExecutionReceipt(
                    tx_hash=None,
                    status="failed",
                    error="DEMO_RECOVERY_ADDRESS not configured",
                )
            return await self.signer.quarantine_transfer(
                original_tx_hash=transfer.tx_hash,
                from_addr=transfer.from_address,
                recovery=recovery,
                amount=transfer.amount,
                paragraph_ref=paragraph_ref,
            )

        return ExecutionReceipt(
            tx_hash=None, status="failed", error=f"unknown action {action}"
        )
