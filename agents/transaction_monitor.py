# pyre-ignore-all-errors
from __future__ import annotations

import time
from collections import deque
from datetime import datetime

from core.compat import LRUCache
from core.models import AgentSignal, TopicName, TransactionEvent


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=None)


class TransactionMonitorAgent:
    """
    Agent 01: monitors transaction velocity, amount thresholds, and beneficiary
    novelty on the raw Kafka transaction stream.
    """

    def __init__(self) -> None:
        self._recent_transactions: LRUCache[str, deque[tuple[datetime, float]]] = LRUCache(maxsize=100000)
        self._known_beneficiaries: LRUCache[str, set[str]] = LRUCache(maxsize=100000)

    def _trim(self, sender: str, now: datetime) -> None:
        if sender not in self._recent_transactions:
            return
        window = self._recent_transactions[sender]
        while window:
            oldest, _ = window[0]
            if (now - oldest).total_seconds() > 300:
                window.popleft()
                continue
            break

    async def evaluate(self, event: TransactionEvent) -> AgentSignal:
        started = time.perf_counter()
        event_time = _parse_time(event.event_time)
        self._trim(event.sender_account, event_time)
        if event.sender_account not in self._recent_transactions:
            self._recent_transactions[event.sender_account] = deque()
        recent_window = self._recent_transactions[event.sender_account]

        recent_count = event.recent_txn_count_5m or len(recent_window)
        recent_amount = event.recent_amount_5m or sum(amount for _, amount in recent_window)

        flags: list[str] = []
        explanation: list[str] = []
        score = 0.0

        if event.amount >= 200_000:
            flags.append("VERY_HIGH_AMOUNT")
            score += 0.35
            explanation.append(f"amount {event.amount:,.0f} exceeds the critical threshold")
        elif event.amount >= 75_000:
            flags.append("HIGH_AMOUNT")
            score += 0.18
            explanation.append(f"amount {event.amount:,.0f} breaches the high-value band")

        if recent_count >= 5:
            flags.append("HIGH_VELOCITY_COUNT")
            score += 0.22
            explanation.append(f"{recent_count} transactions already observed within 5 minutes")

        if recent_amount >= 100_000:
            flags.append("HIGH_VELOCITY_AMOUNT")
            score += 0.2
            explanation.append(f"{recent_amount:,.0f} moved within the rolling 5 minute window")

        if event.sender_account not in self._known_beneficiaries:
            self._known_beneficiaries[event.sender_account] = set()

        if event.new_beneficiary or event.receiver_account not in self._known_beneficiaries[event.sender_account]:
            flags.append("NEW_BENEFICIARY")
            score += 0.14
            explanation.append("beneficiary has not been seen for this sender before")

        if event.transaction_type in {"CRYPTO", "CASH_OUT"} and event.amount >= 50_000:
            flags.append("HIGH_RISK_RAIL")
            score += 0.16
            explanation.append(f"{event.transaction_type} flow carries elevated withdrawal risk")

        if event.amount % 10000 == 0 and event.amount >= 20_000:
            flags.append("ROUND_AMOUNT")
            score += 0.08
            explanation.append("round-value transfer pattern is consistent with mule batching")

        self._known_beneficiaries[event.sender_account].add(event.receiver_account)
        recent_window.append((event_time, event.amount))

        severity = "HIGH" if score >= 0.6 else "MEDIUM" if score >= 0.3 else "LOW"
        topic = TopicName.TXN_ALERT.value if score >= 0.45 else TopicName.TXN_SCORED.value
        return AgentSignal(
            transaction_id=event.transaction_id,
            agent_name="transaction_monitor",
            score=float(f"{min(score, 1.0):.4f}"),
            severity=severity,
            flags=flags,
            evidence={
                "recent_txn_count_5m": recent_count,
                "recent_amount_5m": round(recent_amount, 2),
                "sender_account": event.sender_account,
                "receiver_account": event.receiver_account,
                "amount": event.amount,
            },
            explanation=explanation,
            topic=topic,
            processing_ms=int((time.perf_counter() - started) * 1000),
        )
