"""Circle Developer-Controlled Wallets API client.

Wraps the subset of Circle's Web3 Services API we use to submit MockUSDC enforcement
calls (freeze/refund/quarantine) from a Circle-managed sentinel wallet on Arc Testnet.

Every "critical" request must carry a freshly RSA-OAEP-SHA256-encrypted ciphertext of
the entity secret (the OAEP random padding makes each ciphertext unique even for the
same plaintext). This is Circle's anti-replay design.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from dataclasses import dataclass

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CircleTxResult:
    circle_tx_id: str
    on_chain_tx_hash: str | None
    state: str  # "CONFIRMED" | "FAILED" | "SENT" | ...
    error: str | None = None


class CircleWalletsClient:
    """Async client for Circle Developer-Controlled Wallets."""

    BASE_URL = "https://api.circle.com"

    def __init__(self, api_key: str, entity_secret_hex: str):
        if not api_key or not entity_secret_hex:
            raise ValueError("circle api key and entity secret are both required")
        self._api_key = api_key
        self._secret_hex = entity_secret_hex
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        self._public_key_pem: bytes | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def _public_key(self) -> bytes:
        if self._public_key_pem is None:
            r = await self._client.get("/v1/w3s/config/entity/publicKey")
            r.raise_for_status()
            self._public_key_pem = r.json()["data"]["publicKey"].encode()
        return self._public_key_pem

    async def _fresh_ciphertext(self) -> str:
        pem = await self._public_key()
        pub = serialization.load_pem_public_key(pem)
        ct = pub.encrypt(
            bytes.fromhex(self._secret_hex),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return base64.b64encode(ct).decode()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=4),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True,
    )
    async def submit_contract_execution(
        self,
        wallet_id: str,
        contract_address: str,
        abi_function_signature: str,
        abi_parameters: list,
        fee_level: str = "MEDIUM",
    ) -> str:
        """Submit a contract method call from a developer-controlled wallet.

        Returns the Circle transaction id (not the on-chain hash; poll for that).
        """
        body = {
            "idempotencyKey": str(uuid.uuid4()),
            "entitySecretCiphertext": await self._fresh_ciphertext(),
            "walletId": wallet_id,
            "contractAddress": contract_address,
            "abiFunctionSignature": abi_function_signature,
            "abiParameters": abi_parameters,
            "feeLevel": fee_level,
        }
        r = await self._client.post("/v1/w3s/developer/transactions/contractExecution", json=body)
        if r.status_code >= 400:
            raise RuntimeError(
                f"Circle contractExecution failed ({r.status_code}): {r.text}"
            )
        return r.json()["data"]["id"]

    async def get_transaction(self, tx_id: str) -> dict:
        r = await self._client.get(f"/v1/w3s/transactions/{tx_id}")
        r.raise_for_status()
        return r.json()["data"]["transaction"]

    async def wait_for_confirmation(
        self,
        tx_id: str,
        poll_interval: float = 2.0,
        timeout: float = 120.0,
    ) -> CircleTxResult:
        """Poll until tx reaches a terminal state (CONFIRMED / FAILED / CANCELLED)."""
        deadline = asyncio.get_event_loop().time() + timeout
        terminal = {"CONFIRMED", "COMPLETE", "FAILED", "CANCELLED", "DENIED"}
        while True:
            tx = await self.get_transaction(tx_id)
            state = tx.get("state", "UNKNOWN")
            if state in terminal:
                return CircleTxResult(
                    circle_tx_id=tx_id,
                    on_chain_tx_hash=tx.get("txHash"),
                    state=state,
                    error=tx.get("errorReason"),
                )
            if asyncio.get_event_loop().time() > deadline:
                return CircleTxResult(
                    circle_tx_id=tx_id,
                    on_chain_tx_hash=tx.get("txHash"),
                    state=f"TIMEOUT_in_state_{state}",
                    error=f"did not reach terminal state within {timeout}s",
                )
            await asyncio.sleep(poll_interval)
