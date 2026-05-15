"""Arc Testnet event listener for MockUSDC Transfer events.

Polls the chain every ``POLL_INTERVAL_SECONDS`` seconds for new ``Transfer`` events emitted by
the deployed MockUSDC contract. Each event is parsed into a ``TransferEvent`` Pydantic model
and dispatched (in M1: printed to stdout; in M2+: pushed onto the ManagerAgent queue).

Run from project root:
    python -m backend.chain.listener
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from web3 import Web3
from web3.exceptions import Web3RPCError

from backend.config import PROJECT_ROOT, Settings, get_settings
from backend.store.models import TransferEvent

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3
ABI_PATH = PROJECT_ROOT / "backend" / "chain" / "abi" / "MockUSDC.json"


class TransferListener:
    """Polls the Arc RPC for new MockUSDC Transfer events."""

    def __init__(self, settings: Settings) -> None:
        if not settings.mock_usdc_addr:
            raise RuntimeError("MOCK_USDC_ADDR not set in .env — deploy MockUSDC first")
        self.settings = settings
        self.w3 = Web3(Web3.HTTPProvider(settings.arc_rpc_url))
        abi = json.loads(ABI_PATH.read_text(encoding="utf-8"))
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(settings.mock_usdc_addr),
            abi=abi,
        )
        self.last_block: int | None = None

    async def run(self) -> None:
        if not self.w3.is_connected():
            raise RuntimeError(f"Could not connect to Arc RPC at {self.settings.arc_rpc_url}")

        chain_id = self.w3.eth.chain_id
        logger.info("Connected to chain %s, contract %s", chain_id, self.contract.address)

        self.last_block = self.w3.eth.block_number
        logger.info("Starting from block %s; polling every %ss", self.last_block, POLL_INTERVAL_SECONDS)

        while True:
            try:
                current = self.w3.eth.block_number
                if current > self.last_block:
                    events = self.contract.events.Transfer.get_logs(
                        from_block=self.last_block + 1,
                        to_block=current,
                    )
                    for raw in events:
                        await self._handle_event(raw)
                    self.last_block = current
            except Web3RPCError as exc:
                logger.warning("RPC error: %s — retrying in %ss", exc, POLL_INTERVAL_SECONDS)
            except Exception:
                logger.exception("Unexpected error in listener loop")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _handle_event(self, raw: dict) -> None:
        event = TransferEvent(
            tx_hash=raw["transactionHash"].hex(),
            block_number=raw["blockNumber"],
            log_index=raw["logIndex"],
            from_address=raw["args"]["from"],
            to_address=raw["args"]["to"],
            amount=raw["args"]["value"],
        )
        # M1: stdout sink. M2+: hand off to ManagerAgent.
        print(event.model_dump_json(indent=2), flush=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    settings = get_settings()
    listener = TransferListener(settings)
    asyncio.run(listener.run())


if __name__ == "__main__":
    main()
