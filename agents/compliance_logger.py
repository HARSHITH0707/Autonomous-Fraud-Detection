# pyre-ignore-all-errors
from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path

from core.models import AgentSignal, ComplianceRecord, DecisionEvent, RiskScoreEvent, TransactionEvent


class ComplianceLoggerAgent:
    """
    Agent 06: audit, regulatory, and forensic logging.
    Now includes MongoDB persistence for real-time dashboard tracking.
    """

    def __init__(self, output_dir: str | Path, db_service=None) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db_service = db_service
        self.log_file = self.output_dir / "compliance_log.jsonl"
        self.report_file = self.output_dir / "fraud_report.csv"
        self.audit_dir = self.output_dir / "forensics"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        if not self.report_file.exists():
            with self.report_file.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "transaction_id",
                        "decision",
                        "risk_score",
                        "sender_account",
                        "receiver_account",
                        "amount",
                        "channel",
                        "policy_hits",
                        "regulatory_references",
                    ]
                )

    async def record(
        self,
        event: TransactionEvent,
        signals: list[AgentSignal],
        risk_event: RiskScoreEvent,
        decision_event: DecisionEvent,
    ) -> ComplianceRecord:
        forensic_snapshot = {
            "transaction": event.to_dict(),
            "signals": [signal.to_dict() for signal in signals],
            "risk": risk_event.to_dict(),
            "decision": decision_event.to_dict(),
        }

        def _write_files() -> ComplianceRecord:
            audit_path = self.audit_dir / f"{event.transaction_id}.json"
            audit_path.write_text(json.dumps(forensic_snapshot, indent=2), encoding="utf-8")

            reportable = decision_event.decision.value == "BLOCK" and event.amount >= 10_000
            regulatory_references = []
            if reportable:
                regulatory_references.extend(
                    [
                        "RBI cyber security framework",
                        "RBI digital payment security controls",
                        "FIU-IND suspicious transaction retention",
                    ]
                )

            record = ComplianceRecord(
                transaction_id=event.transaction_id,
                decision=decision_event.decision.value,
                reportable=reportable,
                audit_path=str(audit_path),
                forensic_snapshot={
                    "policy_hits": decision_event.policy_hits,
                    "risk_score": risk_event.composite_risk,
                    "component_scores": risk_event.component_scores,
                },
                regulatory_references=regulatory_references,
            )

            with self.log_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.to_dict()) + "\n")

            with self.report_file.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        event.transaction_id,
                        decision_event.decision.value,
                        risk_event.composite_risk,
                        event.sender_account,
                        event.receiver_account,
                        event.amount,
                        event.channel,
                        "|".join(decision_event.policy_hits),
                        "|".join(regulatory_references),
                    ]
                )

            if self.db_service:
                asyncio.create_task(self.db_service.store_decision(record.to_dict()))

            return record

        return await asyncio.to_thread(_write_files)
