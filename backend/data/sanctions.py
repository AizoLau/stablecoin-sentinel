"""Local sanctions/risk-tagged address lookup.

In production this would query a continuously-updated upstream (OFAC SDN, HKMA gazette,
Chainalysis). For the MVP demo we ship a static JSON guaranteed to trigger the demo
scenarios; HKMA Para 7.2-7.5 traceability is preserved on each entry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SanctionsHit:
    address: str
    tags: tuple[str, ...]
    source: str
    added: str
    paragraph_ref: str


class SanctionsRegistry:
    def __init__(self, json_path: str | Path):
        self._path = Path(json_path)
        self._index: dict[str, SanctionsHit] = {}
        self._load()

    def _load(self) -> None:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        for entry in data.get("entries", []):
            addr = entry["address"].lower()
            self._index[addr] = SanctionsHit(
                address=addr,
                tags=tuple(entry.get("tags", [])),
                source=entry.get("source", ""),
                added=entry.get("added", ""),
                paragraph_ref=entry.get("paragraph_ref", ""),
            )

    def lookup(self, address: str) -> SanctionsHit | None:
        return self._index.get(address.lower())

    def __len__(self) -> int:
        return len(self._index)
