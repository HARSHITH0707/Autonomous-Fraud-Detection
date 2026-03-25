# pyre-ignore-all-errors
from __future__ import annotations

import asyncio
import time

from core.models import AgentSignal, TopicName, TransactionEvent


class GraphFraudDetectorAgent:
    """
    Agent 03: graph-based link analysis backed by Neo4j in production and an
    in-memory graph in tests.
    """

    def __init__(self, graph_backend) -> None:
        self.graph_backend = graph_backend

    def seed_graph(self, frame) -> None:
        self.graph_backend.load(frame)

    async def evaluate(self, event: TransactionEvent) -> AgentSignal:
        started = time.perf_counter()
        inspection = await asyncio.to_thread(self.graph_backend.inspect_transaction, event)
        topic = TopicName.TXN_ALERT.value if inspection.score >= 0.45 else TopicName.TXN_SCORED.value
        severity = "HIGH" if inspection.score >= 0.6 else "MEDIUM" if inspection.score >= 0.3 else "LOW"
        return AgentSignal(
            transaction_id=event.transaction_id,
            agent_name="graph_fraud_detector",
            score=inspection.score,
            severity=severity,
            flags=inspection.flags,
            evidence=inspection.evidence,
            explanation=inspection.explanation,
            topic=topic,
            processing_ms=int((time.perf_counter() - started) * 1000),
        )
