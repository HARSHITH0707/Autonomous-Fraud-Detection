# pyre-ignore-all-errors
from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TopicName(str, Enum):
    TXN_RAW = "txn.raw"
    TXN_SCORED = "txn.scored"
    TXN_ALERT = "txn.alert"
    TXN_RESPONSE = "txn.response"


class DecisionType(str, Enum):
    BLOCK = "BLOCK"
    OTP = "OTP"
    ALLOW = "ALLOW"


@dataclass(slots=True)
class TransactionEvent:
    transaction_id: str
    source: str
    channel: str
    event_time: str
    sender_account: str
    receiver_account: str
    amount: float
    currency: str = "INR"
    transaction_type: str = "TRANSFER"
    device_id: str = ""
    ip_address: str = ""
    login_country: str = "IN"
    home_country: str = "IN"
    device_mismatch: bool = False
    geo_velocity_km: float = 0.0
    new_beneficiary: bool = False
    beneficiary_age_days: int = 0
    login_velocity_10m: int = 0
    recent_txn_count_5m: int = 0
    recent_amount_5m: float = 0.0
    account_tenure_days: int = 0
    labels: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TransactionEvent":
        res_fields: dict[str, Any] = {}
        for f in fields(cls): # type: ignore[arg-type]
            name = str(f.name)
            if name in payload:
                res_fields[name] = payload[name]
                continue
            if f.default is not MISSING:
                res_fields[name] = f.default
            elif f.default_factory is not MISSING:
                res_fields[name] = f.default_factory() # type: ignore[misc]
        if not res_fields.get("event_time"):
            res_fields["event_time"] = utc_now_iso()
        if not res_fields.get("source"):
            res_fields["source"] = payload.get("payment_rail", "unknown")
        if not res_fields.get("channel"):
            res_fields["channel"] = payload.get("source", "unknown")
        res_fields["labels"] = payload.get("labels", {}) or {}
        res_fields["metadata"] = payload.get("metadata", {}) or {}
        return cls(**res_fields) # type: ignore

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) # type: ignore


@dataclass(slots=True)
class AgentSignal:
    transaction_id: str
    agent_name: str
    score: float
    severity: str
    flags: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    explanation: list[str] = field(default_factory=list)
    topic: str = TopicName.TXN_SCORED.value
    processing_ms: int = 0
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RiskScoreEvent:
    transaction_id: str
    composite_risk: float
    model_name: str
    component_scores: dict[str, float]
    feature_vector: dict[str, float]
    explanation: list[str]
    threshold_block: float
    threshold_otp: float
    processing_ms: int = 0
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DecisionEvent:
    transaction_id: str
    decision: DecisionType
    composite_risk: float
    threshold_used: float
    callback_payload: dict[str, Any]
    policy_hits: list[str]
    component_scores: dict[str, float]
    processing_ms: int = 0
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self) # type: ignore
        payload["decision"] = self.decision.value
        return payload


@dataclass(slots=True)
class ComplianceRecord:
    transaction_id: str
    decision: str
    reportable: bool
    audit_path: str
    forensic_snapshot: dict[str, Any]
    regulatory_references: list[str]
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
