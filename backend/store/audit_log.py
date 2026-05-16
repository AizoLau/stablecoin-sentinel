"""Append-only SQLite audit log of (TransferEvent, Decision, ExecutionReceipt) tuples.

Each agent decision and on-chain enforcement attempt is recorded here. Used by the
dashboard /decisions endpoint for historical replay (M3-D) and by post-hoc traceability
reviews (M4). Models HKMA Chapter 9 retention requirement at the schema level — entries
are never updated, only inserted.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, create_engine, select

from backend.store.models import Action, Decision, ExecutionReceipt, TransferEvent

logger = logging.getLogger(__name__)


class AuditRecord(SQLModel, table=True):
    __tablename__ = "audit_records"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    tx_hash: str = Field(index=True)
    block_number: int
    from_address: str = Field(index=True)
    to_address: str = Field(index=True)
    amount: int

    action: str  # Action enum value
    target_address: str
    risk_score: int
    paragraphs_cited_json: str  # JSON-encoded list[str]
    reasoning_md: str

    execution_status: str  # "confirmed" | "failed" | "skipped"
    execution_tx_hash: str | None = None
    execution_error: str | None = None

    @property
    def paragraphs_cited(self) -> list[str]:
        try:
            return json.loads(self.paragraphs_cited_json)
        except json.JSONDecodeError:
            return []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "tx_hash": self.tx_hash,
            "block_number": self.block_number,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "amount": self.amount,
            "action": self.action,
            "target_address": self.target_address,
            "risk_score": self.risk_score,
            "paragraphs_cited": self.paragraphs_cited,
            "reasoning_md": self.reasoning_md,
            "execution_status": self.execution_status,
            "execution_tx_hash": self.execution_tx_hash,
            "execution_error": self.execution_error,
        }


class AuditLog:
    def __init__(self, sqlite_path: str):
        self._path = Path(sqlite_path)
        self._engine = create_engine(f"sqlite:///{self._path}", echo=False)
        SQLModel.metadata.create_all(self._engine)

    def append(
        self,
        transfer: TransferEvent,
        decision: Decision,
        receipt: ExecutionReceipt,
    ) -> int:
        record = AuditRecord(
            tx_hash=transfer.tx_hash,
            block_number=transfer.block_number,
            from_address=transfer.from_address,
            to_address=transfer.to_address,
            amount=transfer.amount,
            action=decision.action.value
            if isinstance(decision.action, Action)
            else str(decision.action),
            target_address=decision.target_address,
            risk_score=decision.risk_score,
            paragraphs_cited_json=json.dumps(decision.paragraphs_cited),
            reasoning_md=decision.reasoning_md,
            execution_status=receipt.status,
            execution_tx_hash=receipt.tx_hash,
            execution_error=receipt.error,
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info("Audit record #%s persisted (action=%s)", record.id, record.action)
            return record.id  # type: ignore[return-value]

    def list_recent(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with Session(self._engine) as session:
            stmt = (
                select(AuditRecord)
                .order_by(AuditRecord.id.desc())  # type: ignore[attr-defined]
                .limit(limit)
                .offset(offset)
            )
            rows = session.exec(stmt).all()
            return [r.to_dict() for r in rows]

    def count(self) -> int:
        with Session(self._engine) as session:
            return len(session.exec(select(AuditRecord.id)).all())
