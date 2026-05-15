"""DeBank Cloud API client for cross-chain address profiling.

Pulls aggregated activity from DeBank's "all-chain" Pro endpoints so the Risk Assessor
agent can evaluate a wallet's history across Ethereum mainnet + L2s + sidechains in
one call rather than querying each chain separately. This is the primary cross-chain
risk profiling source supporting HKMA Para 4.39 (screening) and 5.4 (ongoing monitoring).

The `is_scam` flag DeBank attaches to historical transactions is treated as a strong
direct risk signal — saves us from having to detect those patterns ourselves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AddressProfile:
    address: str
    total_usd_value: float
    chains_used: tuple[str, ...]
    chains_count: int
    tx_count_recent: int
    counterparty_addresses: tuple[str, ...]
    counterparty_count: int
    scam_tx_count: int
    scam_counterparties: tuple[str, ...]
    first_seen_ts: float | None
    last_seen_ts: float | None

    def is_active(self) -> bool:
        return self.tx_count_recent > 0

    def has_scam_history(self) -> bool:
        return self.scam_tx_count > 0


class DeBankClient:
    """Async client wrapping the small slice of DeBank Pro API we need."""

    def __init__(self, accesskey: str, base_url: str = "https://pro-openapi.debank.com"):
        if not accesskey:
            raise ValueError("DEBANK_ACCESSKEY is empty")
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"AccessKey": accesskey},
            timeout=30,
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=5),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def _get(self, path: str, params: dict) -> dict | list:
        r = await self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def get_profile(self, address: str, history_pages: int = 2) -> AddressProfile:
        """Build a cross-chain risk profile for ``address``.

        history_pages: number of 20-tx pages of all_history_list to scan (default 2 = 40 tx).
        """
        addr = address.lower()

        used_chains_raw = await self._get("/v1/user/used_chain_list", {"id": addr})
        total_raw = await self._get("/v1/user/total_balance", {"id": addr})

        # all_history_list pagination: page_count is items per page; we paginate by start_time
        history_items: list[dict] = []
        start_time = 0
        for _ in range(history_pages):
            params = {"id": addr, "page_count": 20}
            if start_time:
                params["start_time"] = start_time
            page = await self._get("/v1/user/all_history_list", params)
            items = page.get("history_list", []) if isinstance(page, dict) else []
            if not items:
                break
            history_items.extend(items)
            # next page anchored at oldest tx in this page
            start_time = min(int(it.get("time_at", 0)) for it in items if it.get("time_at"))
            if start_time == 0:
                break

        counterparties: set[str] = set()
        scam_counterparties: set[str] = set()
        scam_count = 0
        first_ts: float | None = None
        last_ts: float | None = None

        for item in history_items:
            other = (item.get("other_addr") or "").lower()
            if other and other != addr:
                counterparties.add(other)
            if item.get("is_scam"):
                scam_count += 1
                if other:
                    scam_counterparties.add(other)
            ts = item.get("time_at")
            if ts is not None:
                ts = float(ts)
                first_ts = ts if first_ts is None else min(first_ts, ts)
                last_ts = ts if last_ts is None else max(last_ts, ts)

        chains_used = tuple(
            c.get("id", "") for c in used_chains_raw if isinstance(c, dict) and c.get("id")
        )
        total_usd = float(total_raw.get("total_usd_value", 0.0)) if isinstance(total_raw, dict) else 0.0

        return AddressProfile(
            address=addr,
            total_usd_value=total_usd,
            chains_used=chains_used,
            chains_count=len(chains_used),
            tx_count_recent=len(history_items),
            counterparty_addresses=tuple(sorted(counterparties)),
            counterparty_count=len(counterparties),
            scam_tx_count=scam_count,
            scam_counterparties=tuple(sorted(scam_counterparties)),
            first_seen_ts=first_ts,
            last_seen_ts=last_ts,
        )
