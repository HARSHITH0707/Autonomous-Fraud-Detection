import json
import logging
from datetime import datetime
from collections import defaultdict, deque
from typing import Optional

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Agent01-TransactionMonitor")

THRESHOLDS = {
    "high_amount":          50_000,
    "very_high_amount":    200_000,
    "velocity_window_sec":    300,
    "velocity_max_txns":        5,
    "velocity_max_amount":  80_000,
    "night_hours":        (1, 5),
    "suspicious_txn_types": ["CASH_OUT"],
}

ALERT_WEIGHTS = {
    "VERY_HIGH_AMOUNT":    0.50,
    "HIGH_AMOUNT":         0.25,
    "UNUSUAL_HOUR":        0.20,
    "NEW_BENEFICIARY":     0.20,
    "HIGH_VELOCITY_COUNT": 0.35,
    "HIGH_VELOCITY_AMOUNT":0.35,
    "CASH_OUT_LARGE":      0.30,
    "ROUND_AMOUNT":        0.10,
}


class TransactionMonitorAgent:

    def __init__(self):
        self._recent_txns: dict = defaultdict(deque)
        self._known_receivers: dict = defaultdict(set)
        log.info("TransactionMonitorAgent initialized")

    def analyze(self, transaction: dict) -> dict:
        alerts  = []
        details = []

        txn_id   = transaction.get("transaction_id", "UNKNOWN")
        amount   = float(transaction.get("amount", 0))
        sender   = transaction.get("sender_account", "")
        receiver = transaction.get("receiver_account", "")
        txn_type = transaction.get("transaction_type", "")
        ts_raw   = transaction.get("timestamp", datetime.now().isoformat())

        try:
            if isinstance(ts_raw, str):
                ts = datetime.fromisoformat(ts_raw.replace("T", " ").split(".")[0])
            else:
                ts = ts_raw
        except Exception:
            ts = datetime.now()

        if amount >= THRESHOLDS["very_high_amount"]:
            alerts.append("VERY_HIGH_AMOUNT")
            details.append(f"Amount {amount:,.0f} exceeds critical threshold")
        elif amount >= THRESHOLDS["high_amount"]:
            alerts.append("HIGH_AMOUNT")
            details.append(f"Amount {amount:,.0f} exceeds high threshold")

        if amount % 1000 == 0 and amount >= 10_000:
            alerts.append("ROUND_AMOUNT")
            details.append(f"Suspiciously round amount: {amount:,.0f}")

        hour = ts.hour
        night_start, night_end = THRESHOLDS["night_hours"]
        if night_start <= hour <= night_end:
            alerts.append("UNUSUAL_HOUR")
            details.append(f"Transaction at {hour:02d}:00 — suspicious hours")

        if receiver and receiver not in self._known_receivers[sender]:
            alerts.append("NEW_BENEFICIARY")
            details.append(f"Receiver {receiver} is NEW for sender {sender}")

        self._clean_old_txns(sender, ts)
        recent = self._recent_txns[sender]
        recent_count  = len(recent)
        recent_amount = sum(r["amount"] for r in recent)

        if recent_count >= THRESHOLDS["velocity_max_txns"]:
            alerts.append("HIGH_VELOCITY_COUNT")
            details.append(f"Sender made {recent_count} txns in last 5 minutes")

        if recent_amount >= THRESHOLDS["velocity_max_amount"]:
            alerts.append("HIGH_VELOCITY_AMOUNT")
            details.append(f"Sender sent {recent_amount:,.0f} in last 5 minutes")

        if txn_type in THRESHOLDS["suspicious_txn_types"] and amount >= 20_000:
            alerts.append("CASH_OUT_LARGE")
            details.append(f"Large CASH_OUT of {amount:,.0f}")

        self._known_receivers[sender].add(receiver)
        self._recent_txns[sender].append({
            "timestamp": ts,
            "amount":    amount,
            "txn_id":    txn_id
        })

        alert_score = min(
            sum(ALERT_WEIGHTS.get(a, 0.1) for a in alerts),
            1.0
        )

        result = {
            "agent":          "TransactionMonitor",
            "transaction_id": txn_id,
            "sender":         sender,
            "receiver":       receiver,
            "amount":         amount,
            "timestamp":      ts.isoformat(),
            "alerts":         alerts,
            "alert_count":    len(alerts),
            "alert_score":    round(alert_score, 4),
            "details":        details,
            "flagged":        alert_score >= 0.3,
        }

        if alerts:
            log.warning(f"[{txn_id}] {len(alerts)} alerts | score={alert_score:.2f}")
        else:
            log.info(f"[{txn_id}] Clean transaction")

        return result

    def analyze_batch(self, transactions: list) -> list:
        return [self.analyze(txn) for txn in transactions]

    def get_summary(self, results: list) -> dict:
        total   = len(results)
        flagged = sum(1 for r in results if r["flagged"])
        alert_counts = defaultdict(int)
        for r in results:
            for a in r["alerts"]:
                alert_counts[a] += 1
        return {
            "total_analyzed":  total,
            "flagged":         flagged,
            "clean":           total - flagged,
            "flag_rate":       round(flagged / max(total, 1) * 100, 2),
            "top_alerts":      dict(sorted(alert_counts.items(),
                                           key=lambda x: x[1], reverse=True)),
        }

    def _clean_old_txns(self, account_id: str, current_ts: datetime):
        window_sec = THRESHOLDS["velocity_window_sec"]
        recent = self._recent_txns[account_id]
        while recent:
            oldest_ts = recent[0]["timestamp"]
            if isinstance(oldest_ts, str):
                oldest_ts = datetime.fromisoformat(oldest_ts)
            age = (current_ts - oldest_ts).total_seconds()
            if age > window_sec:
                recent.popleft()
            else:
                break


if __name__ == "__main__":
    agent = TransactionMonitorAgent()
    test_txns = [
        {
            "transaction_id":   "TXN_TEST_001",
            "timestamp":        "2024-03-15T03:30:00",
            "sender_account":   "ACC000123",
            "receiver_account": "ACC000999",
            "amount":           250000,
            "transaction_type": "CASH_OUT",
            "device_id":        "device-abc",
            "ip_address":       "192.168.1.1",
            "is_fraud":         1
        },
        {
            "transaction_id":   "TXN_TEST_002",
            "timestamp":        "2024-03-15T14:00:00",
            "sender_account":   "ACC000456",
            "receiver_account": "ACC000789",
            "amount":           500,
            "transaction_type": "TRANSFER",
            "device_id":        "device-xyz",
            "ip_address":       "192.168.1.2",
            "is_fraud":         0
        },
    ]
    print("\n" + "="*60)
    print("  AGENT 01 - Transaction Monitor Test")
    print("="*60)
    results = agent.analyze_batch(test_txns)
    for r in results:
        print(f"\nTransaction: {r['transaction_id']}")
        print(f"  Score:   {r['alert_score']}")
        print(f"  Flagged: {r['flagged']}")
        print(f"  Alerts:  {r['alerts']}")
