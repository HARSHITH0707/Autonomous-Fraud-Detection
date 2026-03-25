# pyre-ignore-all-errors
from __future__ import annotations

import asyncio
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from core.compat import LRUCache, optional_import_attr

from core.models import AgentSignal, TopicName, TransactionEvent

IsolationForest = optional_import_attr("sklearn.ensemble", "IsolationForest")


@dataclass(slots=True)
class BehaviourProfile:
    account_id: str
    countries: Counter[str] = field(default_factory=lambda: Counter())
    devices: Counter[str] = field(default_factory=lambda: Counter())
    amounts: list[float] = field(default_factory=list)
    ip_prefixes: Counter[str] = field(default_factory=lambda: Counter())

    def update(self, event: TransactionEvent) -> None:
        self.countries[event.login_country] += 1
        self.devices[event.device_id] += 1
        self.amounts.append(event.amount)
        ip_prefix = ".".join(event.ip_address.split(".")[:2]) if event.ip_address else "unknown"
        self.ip_prefixes[ip_prefix] += 1

    @property
    def avg_amount(self) -> float:
        return float(statistics.fmean(self.amounts)) if self.amounts else 0.0

    @property
    def std_amount(self) -> float:
        return float(statistics.pstdev(self.amounts)) if len(self.amounts) > 1 else 0.0


class BehaviourAnalyserAgent:
    """
    Agent 02: login, device, and geo-behaviour anomaly detection.
    """

    def __init__(self) -> None:
        self.profiles: LRUCache[str, BehaviourProfile] = LRUCache(maxsize=100000)
        self.model: Any | None = (
            IsolationForest(
                n_estimators=100,
                contamination=0.04,
                random_state=42,
            )
            if IsolationForest is not None
            else None
        )
        self._bootstrap_ready = False

    @staticmethod
    def _vectorise(event: TransactionEvent) -> list[float]:
        return [
            float(event.amount),
            1.0 if event.device_mismatch else 0.0,
            float(event.geo_velocity_km),
            1.0 if event.new_beneficiary else 0.0,
            float(event.beneficiary_age_days),
            float(event.login_velocity_10m),
            float(event.recent_txn_count_5m),
        ]

    def bootstrap(self, history: Iterable[TransactionEvent]) -> None:
        events = list(history)
        if not events:
            return
        model = self.model
        if model is not None and len(events) >= 16:
            try:
                model.fit([self._vectorise(event) for event in events])
            except Exception:
                self._bootstrap_ready = False
            else:
                self._bootstrap_ready = True
        for event in events:
            if event.sender_account not in self.profiles:
                self.profiles[event.sender_account] = BehaviourProfile(event.sender_account)
            self.profiles[event.sender_account].update(event)

    async def evaluate(self, event: TransactionEvent) -> AgentSignal:
        started = time.perf_counter()
        if event.sender_account not in self.profiles:
            self.profiles[event.sender_account] = BehaviourProfile(event.sender_account)
        profile = self.profiles[event.sender_account]

        flags: list[str] = []
        explanation: list[str] = []
        score = 0.0

        if event.login_country and event.login_country != event.home_country:
            flags.append("FOREIGN_LOGIN")
            score += 0.2
            explanation.append(f"login country shifted from {event.home_country} to {event.login_country}")

        if event.device_mismatch:
            flags.append("DEVICE_MISMATCH")
            score += 0.23
            explanation.append("device fingerprint does not match the trusted device set")

        if profile.devices and event.device_id not in profile.devices:
            flags.append("NEW_DEVICE")
            score += 0.16
            explanation.append("device has not been used previously by this account")

        if profile.countries and event.login_country not in profile.countries:
            flags.append("NEW_GEO")
            score += 0.14
            explanation.append("geography does not match the established login pattern")

        if event.geo_velocity_km >= 900:
            flags.append("IMPOSSIBLE_TRAVEL")
            score += 0.22
            explanation.append(f"geo-velocity of {event.geo_velocity_km:,.0f} km indicates impossible travel")

        if profile.amounts:
            std_amount = profile.std_amount
            if std_amount > 0:
                z_score = (event.amount - profile.avg_amount) / max(std_amount, 1.0)
                if z_score >= 3.0:
                    flags.append("AMOUNT_SPIKE")
                    score += 0.16
                    explanation.append(f"transaction amount is {z_score:.1f} standard deviations above baseline")
            elif event.amount > profile.avg_amount * 5:
                flags.append("AMOUNT_SPIKE")
                score += 0.16
                explanation.append("transaction amount is multiple times above baseline")

        if event.login_velocity_10m >= 3:
            flags.append("LOGIN_BURST")
            score += 0.12
            explanation.append(f"{event.login_velocity_10m} login attempts observed within 10 minutes")

        anomaly_score = 0.0
        model = self.model
        if self._bootstrap_ready and model is not None:
            try:
                anomaly_predictions = await asyncio.to_thread(model.decision_function, [self._vectorise(event)])
            except Exception:
                anomaly_score = 0.0
            else:
                anomaly_score = -float(anomaly_predictions[0])
                if anomaly_score > 0.1:
                    flags.append("ISOLATION_FOREST_OUTLIER")
                    score += min(0.2 + anomaly_score, 0.28)
                    explanation.append("unsupervised behaviour model classified the session as an outlier")

        profile.update(event)
        severity = "HIGH" if score >= 0.6 else "MEDIUM" if score >= 0.3 else "LOW"
        topic = TopicName.TXN_ALERT.value if score >= 0.45 else TopicName.TXN_SCORED.value
        return AgentSignal(
            transaction_id=event.transaction_id,
            agent_name="behaviour_analyser",
            score=float(f"{min(score, 1.0):.4f}"),
            severity=severity,
            flags=flags,
            evidence={
                "avg_amount": float(f"{profile.avg_amount:.2f}"),
                "std_amount": float(f"{profile.std_amount:.2f}"),
                "known_devices": len(profile.devices),
                "known_countries": list(profile.countries.keys()),
                "isolation_forest_margin": float(f"{anomaly_score:.4f}"),
            },
            explanation=explanation,
            topic=topic,
            processing_ms=int((time.perf_counter() - started) * 1000),
        )
