"""Pydantic models for transfer events, agent risk profiles, decisions, and execution receipts.

These models flow between the chain listener, agent pipeline, and audit log. They are
the single source of truth for inter-module contracts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class TransferEvent(BaseModel):
    """A single MockUSDC.Transfer event observed on Arc."""

    tx_hash: str
    block_number: int
    log_index: int
    from_address: str
    to_address: str
    amount: int
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RiskFlag(str, Enum):
    SANCTIONS_MATCH = "sanctions_match"
    MIXER_TAG = "mixer_tag"
    SHELL_VASP = "shell_vasp"
    LOW_AGE = "low_age"
    HIGH_VELOCITY = "high_velocity"
    CROSS_CHAIN_TAINT = "cross_chain_taint"


class RiskProfile(BaseModel):
    """Output of RiskAssessor agent for a single address."""

    address: str
    score: int = Field(ge=0, le=100)
    age_days: int | None = None
    tx_count_30d: int | None = None
    counterparty_count_30d: int | None = None
    flags: list[RiskFlag] = Field(default_factory=list)
    cross_chain_summary: str | None = None


class Action(str, Enum):
    PASS = "pass"
    REFUND = "refund"
    QUARANTINE = "quarantine"
    FREEZE = "freeze"


class Decision(BaseModel):
    """Output of ComplianceDecider; consumed by ExecutorAgent."""

    transfer: TransferEvent
    action: Action
    target_address: str
    risk_score: int
    paragraphs_cited: list[str]
    reasoning_md: str


class ExecutionReceipt(BaseModel):
    """Result of an on-chain enforcement action."""

    tx_hash: str | None
    status: str  # "submitted" | "confirmed" | "failed" | "skipped"
    gas_used: int | None = None
    error: str | None = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
