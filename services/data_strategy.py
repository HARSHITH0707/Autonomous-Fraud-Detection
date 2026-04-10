from __future__ import annotations

import csv
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from core.compat import clip, optional_import, percentile_rank, read_csv_records, safe_float, safe_int, stable_bucket
from core.config import NetworkSettings
from core.models import TransactionEvent

pd = optional_import("pandas")


def _default_graph_rows() -> list[dict[str, Any]]:
    return [
        {
            "transaction_id": "SG-0001",
            "timestamp": "2024-03-01T10:00:00",
            "sender_account": "ACC-MULE-1",
            "receiver_account": "ACC-MULE-2",
            "amount": 50000,
            "transaction_type": "TRANSFER",
            "device_id": "shared-device-1",
            "ip_address": "45.1.1.1",
            "is_fraud": 1,
        },
        {
            "transaction_id": "SG-0002",
            "timestamp": "2024-03-01T10:02:00",
            "sender_account": "ACC-MULE-2",
            "receiver_account": "ACC-MULE-3",
            "amount": 49000,
            "transaction_type": "TRANSFER",
            "device_id": "shared-device-1",
            "ip_address": "45.1.1.2",
            "is_fraud": 1,
        },
        {
            "transaction_id": "SG-0003",
            "timestamp": "2024-03-01T10:03:00",
            "sender_account": "ACC-MULE-3",
            "receiver_account": "ACC-MULE-HUB",
            "amount": 48000,
            "transaction_type": "TRANSFER",
            "device_id": "shared-device-2",
            "ip_address": "45.1.1.3",
            "is_fraud": 1,
        },
        {
            "transaction_id": "SG-0004",
            "timestamp": "2024-03-01T10:05:00",
            "sender_account": "ACC-RING-1",
            "receiver_account": "ACC-RING-2",
            "amount": 36000,
            "transaction_type": "TRANSFER",
            "device_id": "ring-device-1",
            "ip_address": "45.2.1.1",
            "is_fraud": 1,
        },
        {
            "transaction_id": "SG-0005",
            "timestamp": "2024-03-01T10:06:00",
            "sender_account": "ACC-RING-2",
            "receiver_account": "ACC-RING-3",
            "amount": 35500,
            "transaction_type": "TRANSFER",
            "device_id": "ring-device-1",
            "ip_address": "45.2.1.2",
            "is_fraud": 1,
        },
        {
            "transaction_id": "SG-0006",
            "timestamp": "2024-03-01T10:07:00",
            "sender_account": "ACC-RING-3",
            "receiver_account": "ACC-RING-1",
            "amount": 35200,
            "transaction_type": "TRANSFER",
            "device_id": "ring-device-2",
            "ip_address": "45.2.1.3",
            "is_fraud": 1,
        },
    ]


def _to_frame(rows: list[dict[str, Any]]) -> Any:
    if pd is None:
        return rows
    return pd.DataFrame(rows)


def _merge_on_key(left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    right_index = {str(row.get(key, "")): row for row in right_rows}
    merged: list[dict[str, Any]] = []
    for row in left_rows:
        record = dict(row)
        record.update(right_index.get(str(row.get(key, "")), {}))
        merged.append(record)
    return merged


@dataclass(slots=True)
class DataStrategy:
    settings: NetworkSettings

    @property
    def ieee_transaction_path(self) -> Path:
        return self.settings.data_dir / "IEEE-Dataset" / "train_transaction.csv"

    @property
    def ieee_identity_path(self) -> Path:
        return self.settings.data_dir / "IEEE-Dataset" / "train_identity.csv"

    @property
    def paysim_path(self) -> Path:
        return self.settings.data_dir / "SyntheticFindataset" / "PS_20174392719_1491204439457_log.csv"

    @property
    def synthetic_graph_path(self) -> Path:
        return self.settings.data_dir / "synthetic_fraud_graph_dataset.csv"

    def describe(self) -> dict[str, str]:
        return {
            "ieee_cis": "Supervised learning corpus for XGBoost risk scoring using labelled card fraud patterns.",
            "paysim": "High-volume mobile money stream used to replay Kafka-style transaction events.",
            "synthetic_graph": "Fraud-ring, mule-chain, and shared-device graph seed for Neo4j traversal tests.",
        }

    @staticmethod
    def _paysim_row_to_event(row: dict[str, Any], absolute_index: int, base_time: datetime) -> TransactionEvent:
        amount = safe_float(row.get("amount"))
        step = safe_int(row.get("step"))
        sender = str(row.get("nameOrig", ""))
        is_fraud = safe_int(row.get("isFraud"))
        risky_destination = is_fraud == 1 and absolute_index % 3 == 0
        receiver = "ACC-MULE-1" if risky_destination else str(row.get("nameDest", ""))
        login_country = "AE" if is_fraud == 1 and absolute_index % 2 == 0 else "IN"
        device_mismatch = bool(is_fraud == 1 and absolute_index % 2 == 0)
        geo_velocity = 1800.0 if is_fraud == 1 else 0.0
        login_velocity = 4 if is_fraud == 1 else absolute_index % 3
        recent_txn_count = 6 if is_fraud == 1 else absolute_index % 5
        recent_amount = max(amount * 4, 120000.0) if is_fraud == 1 else amount * max(1, absolute_index % 4)
        beneficiary_age_days = 0 if is_fraud == 1 else absolute_index % 45
        return TransactionEvent(
            transaction_id=f"PAYSIM-{absolute_index:06d}",
            source="paysim",
            channel=str(row.get("type", "transfer")).lower(),
            event_time=(base_time + timedelta(hours=step)).isoformat(),
            sender_account=sender,
            receiver_account=receiver,
            amount=amount,
            currency="INR",
            transaction_type=str(row.get("type", "TRANSFER")),
            device_id=f"device-{stable_bucket(sender, 1000):04d}",
            ip_address=f"10.{stable_bucket(sender, 200)}.{stable_bucket(receiver, 200)}.8",
            login_country=login_country,
            home_country="IN",
            device_mismatch=device_mismatch,
            geo_velocity_km=geo_velocity,
            new_beneficiary=bool(is_fraud == 1 or absolute_index % 7 == 0),
            beneficiary_age_days=beneficiary_age_days,
            login_velocity_10m=login_velocity,
            recent_txn_count_5m=recent_txn_count,
            recent_amount_5m=recent_amount,
            account_tenure_days=365,
            labels={"is_fraud": is_fraud},
            metadata={"stream_source": "paysim"},
        )

    def _synthetic_replay_stream(self, max_rows: int = 500, start_index: int = 0) -> Iterator[TransactionEvent]:
        base_time = datetime(2024, 3, 2, 9, 0, 0)
        for offset in range(max_rows):
            absolute_index = start_index + offset
            pattern = absolute_index % 6
            event_time = (base_time + timedelta(minutes=absolute_index)).isoformat()

            if pattern in {0, 5}:
                yield TransactionEvent(
                    transaction_id=f"SIM-{absolute_index:06d}",
                    source="synthetic-replay",
                    channel="upi",
                    event_time=event_time,
                    sender_account=f"ACC-RING-{(absolute_index % 3) + 1}",
                    receiver_account="ACC-MULE-1",
                    amount=185000.0 + float((absolute_index % 4) * 7500),
                    currency="INR",
                    transaction_type="TRANSFER",
                    device_id=f"device-burner-{absolute_index % 9:02d}",
                    ip_address=f"196.12.55.{10 + (absolute_index % 20)}",
                    login_country="AE",
                    home_country="IN",
                    device_mismatch=True,
                    geo_velocity_km=2400.0,
                    new_beneficiary=True,
                    beneficiary_age_days=0,
                    login_velocity_10m=4,
                    recent_txn_count_5m=6,
                    recent_amount_5m=225000.0,
                    account_tenure_days=420,
                    metadata={"stream_source": "synthetic-fallback", "risk_band": "high"},
                )
                continue

            if pattern in {1, 4}:
                yield TransactionEvent(
                    transaction_id=f"SIM-{absolute_index:06d}",
                    source="synthetic-replay",
                    channel="upi",
                    event_time=event_time,
                    sender_account=f"ACC-OTP-{absolute_index % 5}",
                    receiver_account="ACC-MULE-1",
                    amount=40000.0 + float((absolute_index % 3) * 5000),
                    currency="INR",
                    transaction_type="TRANSFER",
                    device_id=f"device-home-{absolute_index % 4:02d}",
                    ip_address=f"103.44.{20 + (absolute_index % 5)}.{10 + (absolute_index % 10)}",
                    login_country="AE",
                    home_country="IN",
                    device_mismatch=False,
                    geo_velocity_km=120.0,
                    new_beneficiary=True,
                    beneficiary_age_days=0,
                    login_velocity_10m=2,
                    recent_txn_count_5m=2,
                    recent_amount_5m=55000.0,
                    account_tenure_days=365,
                    metadata={"stream_source": "synthetic-fallback", "risk_band": "medium"},
                )
                continue

            yield TransactionEvent(
                transaction_id=f"SIM-{absolute_index:06d}",
                source="synthetic-replay",
                channel="upi",
                event_time=event_time,
                sender_account="ACC-PRIMARY",
                receiver_account=f"ACC-KNOWN-{absolute_index % 6}",
                amount=1800.0 + float((absolute_index % 5) * 250),
                currency="INR",
                transaction_type="TRANSFER",
                device_id="device-home",
                ip_address="103.44.12.8",
                login_country="IN",
                home_country="IN",
                device_mismatch=False,
                geo_velocity_km=0.0,
                new_beneficiary=False,
                beneficiary_age_days=45,
                login_velocity_10m=1,
                recent_txn_count_5m=1,
                recent_amount_5m=2500.0,
                account_tenure_days=450,
                metadata={"stream_source": "synthetic-fallback", "risk_band": "low"},
            )

    def replay_stream_events(self, max_rows: int = 500, start_index: int = 0) -> tuple[list[TransactionEvent], str]:
        if self.paysim_path.exists():
            frame_rows = read_csv_records(self.paysim_path, limit=start_index + max_rows)
            rows = frame_rows[start_index:start_index + max_rows]
            if rows:
                base_time = datetime(2024, 3, 1)
                return (
                    [self._paysim_row_to_event(row, start_index + index, base_time) for index, row in enumerate(rows)],
                    "paysim",
                )

        return (list(self._synthetic_replay_stream(max_rows=max_rows, start_index=start_index)), "synthetic-fallback")

    def supervised_training_frame(self, max_rows: int = 5000) -> Any:
        if not self.ieee_transaction_path.exists():
            return _to_frame([])

        transactions = read_csv_records(self.ieee_transaction_path, limit=max_rows)
        if self.ieee_identity_path.exists():
            identity = read_csv_records(self.ieee_identity_path, limit=max_rows)
            rows = _merge_on_key(transactions, identity, "TransactionID")
        else:
            rows = transactions

        card_values = [safe_float(row.get("card1")) for row in rows]
        addr_values = [safe_float(row.get("addr1")) for row in rows]
        addr_median = statistics.median(addr_values) if addr_values else 0.0

        result_rows: list[dict[str, float | int]] = []
        previous_transaction_dt: float | None = None
        for row in rows:
            transaction_amt = safe_float(row.get("TransactionAmt"))
            transaction_dt = safe_float(row.get("TransactionDT"))
            diff = abs(transaction_dt - previous_transaction_dt) if previous_transaction_dt is not None else 0.0
            previous_transaction_dt = transaction_dt

            result_rows.append(
                {
                    "transaction_monitor": clip(transaction_amt / 5000.0),
                    "behaviour_analyser": clip(safe_float(row.get("dist1")) / 100.0),
                    "graph_fraud_detector": percentile_rank(card_values, safe_float(row.get("card1"))),
                    "amount_scaled": clip(transaction_amt / 10_000.0),
                    "device_mismatch": 1.0 if str(row.get("DeviceType", "desktop")).lower() == "mobile" else 0.0,
                    "new_beneficiary": 1.0 if safe_float(row.get("addr1")) > addr_median else 0.0,
                    "geo_velocity_scaled": clip(safe_float(row.get("dist2")) / 100.0),
                    "login_velocity_scaled": clip(diff / 10_000.0),
                    "is_fraud": safe_int(row.get("isFraud")),
                }
            )
        return _to_frame(result_rows)

    def paysim_stream(self, max_rows: int = 500, start_index: int = 0) -> Iterator[TransactionEvent]:
        if not self.paysim_path.exists():
            return iter(())

        frame_rows = read_csv_records(self.paysim_path, limit=start_index + max_rows)
        rows = frame_rows[start_index:start_index + max_rows]
        base_time = datetime(2024, 3, 1)
        for index, row in enumerate(rows):
            yield self._paysim_row_to_event(row, start_index + index, base_time)

    def synthetic_graph_seed(self, max_rows: int = 1000) -> Any:
        if self.synthetic_graph_path.exists():
            rows = read_csv_records(self.synthetic_graph_path)
            fraud_rows = [row for row in rows if safe_int(row.get("is_fraud")) == 1]
            if len(rows) <= max_rows:
                selected_rows = rows
            else:
                head_budget = max(max_rows - len(fraud_rows), 0)
                selected_rows = rows[:head_budget] + fraud_rows[:max_rows]
            deduped_rows: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for row in selected_rows:
                row_id = str(row.get("transaction_id", "") or "")
                if row_id and row_id in seen_ids:
                    continue
                if row_id:
                    seen_ids.add(row_id)
                deduped_rows.append(row)
            required_ids = {row["transaction_id"] for row in _default_graph_rows()}
            present_ids = {str(row.get("transaction_id", "") or "") for row in deduped_rows}
            for row in _default_graph_rows():
                if row["transaction_id"] not in present_ids:
                    deduped_rows.append(row)
            return _to_frame(deduped_rows[:max_rows])

        return _to_frame(_default_graph_rows())

    def bootstrap_history(self, count: int = 80) -> list[TransactionEvent]:
        history = []
        if self.paysim_path.exists():
            history = list(self.paysim_stream(max_rows=count))
        if history:
            return history

        base_time = datetime(2024, 3, 1, 9, 0, 0)
        for idx in range(count):
            history.append(
                TransactionEvent(
                    transaction_id=f"HIST-{idx:04d}",
                    source="bootstrap",
                    channel="upi",
                    event_time=(base_time + timedelta(minutes=idx)).isoformat(),
                    sender_account="ACC-PRIMARY",
                    receiver_account=f"ACC-KNOWN-{idx % 6}",
                    amount=500 + float(idx % 10) * 25,
                    device_id="device-home",
                    ip_address="103.44.12.8",
                    login_country="IN",
                    home_country="IN",
                    beneficiary_age_days=30 + (idx % 10),
                    recent_txn_count_5m=idx % 3,
                    recent_amount_5m=700 + idx * 5,
                    account_tenure_days=450,
                )
            )
        return history

    def proof_of_concept_event(self) -> TransactionEvent:
        return TransactionEvent(
            transaction_id="POC-FOREIGN-LOGIN-001",
            source="realtime",
            channel="upi",
            event_time="2026-03-24T18:42:00+05:30",
            sender_account="ACC-PRIMARY",
            receiver_account="ACC-MULE-1",
            amount=185000.0,
            currency="INR",
            transaction_type="TRANSFER",
            device_id="device-burner-77",
            ip_address="196.12.55.10",
            login_country="AE",
            home_country="IN",
            device_mismatch=True,
            geo_velocity_km=2460.0,
            new_beneficiary=True,
            beneficiary_age_days=0,
            login_velocity_10m=4,
            recent_txn_count_5m=6,
            recent_amount_5m=231000.0,
            account_tenure_days=420,
            metadata={
                "scenario": "foreign_login_large_transfer",
                "beneficiary_type": "new",
            },
        )
