# pyre-ignore-all-errors
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

from agents import (
    BehaviourAnalyserAgent,
    ComplianceLoggerAgent,
    DecisionEngineAgent,
    GraphFraudDetectorAgent,
    RiskScorerAgent,
    TransactionMonitorAgent,
)
from core.compat import optional_import
from core.config import NetworkSettings
from core.models import AgentSignal, DecisionEvent, DecisionType, RiskScoreEvent, TopicName, TransactionEvent
from graph.neo4j_graph import InMemoryFraudGraph, build_graph_backend
from services.data_strategy import DataStrategy
from streaming import InMemoryKafkaBroker
from core.db_service import MongoDBService

_langgraph = optional_import("langgraph.graph")
END = getattr(_langgraph, "END", None)
START = getattr(_langgraph, "START", None)
StateGraph = getattr(_langgraph, "StateGraph", None)


@dataclass(slots=True)
class NetworkRunResult:
    transaction: dict[str, Any]
    signals: dict[str, dict[str, Any]]
    risk: dict[str, Any]
    decision: dict[str, Any]
    compliance: dict[str, Any]
    topics: dict[str, list[dict[str, Any]]]
    orchestration_engine: str

    def to_dict(self, mask_sensitive: bool = False) -> dict[str, Any]:
        transaction_data = self.transaction.copy() if mask_sensitive else self.transaction
        
        if mask_sensitive:
            for field_name in ["sender_account", "receiver_account"]:
                val = str(transaction_data.get(field_name, ""))
                if len(val) > 4:
                    transaction_data[field_name] = "***" + val[-4:]
                elif val:
                    transaction_data[field_name] = "***"
                    
            ip = str(transaction_data.get("ip_address", ""))
            if ip and len(ip.split(".")) == 4:
                parts = ip.split(".")
                transaction_data["ip_address"] = f"{parts[0]}.{parts[1]}.***.***"
                
        return {
            "transaction": transaction_data,
            "signals": self.signals,
            "risk": self.risk,
            "decision": self.decision,
            "compliance": self.compliance,
            "topics": self.topics,
            "orchestration_engine": self.orchestration_engine,
        }


class FraudDetectionNetwork:
    def __init__(self, settings: NetworkSettings | None = None, broker: InMemoryKafkaBroker | None = None) -> None:
        self.settings = settings or NetworkSettings()
        self.broker = broker or InMemoryKafkaBroker()
        self.db_service = MongoDBService(self.settings.mongodb_uri, self.settings.mongodb_db)
        self.data_strategy = DataStrategy(self.settings)
        self.graph_backend = build_graph_backend(
            use_neo4j=self.settings.use_neo4j,
            uri=self.settings.neo4j_uri,
            user=self.settings.neo4j_user,
            password=self.settings.neo4j_password,
        )
        self.transaction_monitor = TransactionMonitorAgent()
        self.behaviour_analyser = BehaviourAnalyserAgent(db_service=self.db_service)
        self.graph_detector = GraphFraudDetectorAgent(self.graph_backend)
        self.risk_scorer = RiskScorerAgent(
            model_dir=self.settings.model_dir,
            block_threshold=self.settings.decision_block_threshold,
            otp_threshold=self.settings.decision_otp_threshold,
        )
        self.decision_engine = DecisionEngineAgent(
            block_threshold=self.settings.decision_block_threshold,
            otp_threshold=self.settings.decision_otp_threshold,
        )
        self.compliance_logger = ComplianceLoggerAgent(self.settings.output_dir, db_service=self.db_service)
        self.orchestration_engine = "langgraph" if StateGraph is not None else "sequential-fallback"
        self._bootstrapped = False
        self._circuit_breakers: dict[str, dict[str, Any]] = {}

    def _switch_graph_backend_to_in_memory(self, reason: object, seed_frame: Any | None = None) -> bool:
        if isinstance(self.graph_backend, InMemoryFraudGraph):
            return True

        try:
            fallback_backend = build_graph_backend(use_neo4j=False)
            fallback_backend.load(seed_frame if seed_frame is not None else self.data_strategy.synthetic_graph_seed())
        except Exception as exc:
            log.error("Graph in-memory fallback failed after %s: %s", reason, exc)
            return False

        log.warning("Switching graph backend to in-memory fallback after %s", reason)
        self.graph_backend = fallback_backend
        self.graph_detector.graph_backend = fallback_backend
        self.settings.use_neo4j = False
        return True

    def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        try:
            self.behaviour_analyser.bootstrap(self.data_strategy.bootstrap_history())
        except Exception as exc:
            log.warning("Behaviour Analyser bootstrap failed: %s", exc)
        graph_seed = self.data_strategy.synthetic_graph_seed()
        try:
            self.graph_detector.seed_graph(graph_seed)
        except Exception as exc:
            log.warning("Graph Detector bootstrap failed: %s", exc)
            self._switch_graph_backend_to_in_memory(exc, seed_frame=graph_seed)
        training_frame = self.data_strategy.supervised_training_frame(max_rows=4000)
        is_empty = getattr(training_frame, "empty", None)
        has_training_rows = (is_empty is False) if is_empty is not None else bool(training_frame)
        if has_training_rows:
            try:
                self.risk_scorer.model.fit(training_frame, "is_fraud")
            except Exception as exc:
                log.warning("Risk Scorer bootstrap failed: %s", exc)
        self._bootstrapped = True

    async def _safe_eval(self, agent: Any, event: TransactionEvent, default_name: str) -> AgentSignal:
        cb = self._circuit_breakers.setdefault(default_name, {"failures": 0, "last_failure": 0.0})
        if cb["failures"] >= 3 and time.time() - cb["last_failure"] < 30.0:
            return AgentSignal(
                transaction_id=event.transaction_id,
                agent_name=default_name,
                score=0.0,
                severity="LOW",
                flags=[f"CIRCUIT_BREAKER_OPEN: Agent skipped"],
                topic=TopicName.TXN_SCORED.value
            )
            
        try:
            result = await asyncio.wait_for(agent.evaluate(event), timeout=2.0)
            cb["failures"] = 0
            return result
        except Exception as exc:
            if default_name == "graph_fraud_detector" and self._switch_graph_backend_to_in_memory(exc):
                try:
                    result = await asyncio.wait_for(agent.evaluate(event), timeout=1.0)
                    cb["failures"] = 0
                    return result
                except Exception as fallback_exc:
                    exc = fallback_exc
            cb["failures"] += 1
            cb["last_failure"] = time.time()
            log.error("Agent %s failed: %s", default_name, exc)
            return AgentSignal(
                transaction_id=event.transaction_id,
                agent_name=default_name,
                score=0.0,
                severity="LOW",
                flags=[f"EVAL_FAILED: {type(exc).__name__}"],
                topic=TopicName.TXN_SCORED.value
            )

    async def process_event(self, event: TransactionEvent) -> NetworkRunResult:
        self.bootstrap()
        await self.broker.publish(TopicName.TXN_RAW.value, event.to_dict(), key=event.transaction_id)

        signals = await asyncio.gather(
            self._safe_eval(self.transaction_monitor, event, "transaction_monitor"),
            self._safe_eval(self.behaviour_analyser, event, "behaviour_analyser"),
            self._safe_eval(self.graph_detector, event, "graph_fraud_detector"),
        )
        await asyncio.gather(*(
            self.broker.publish(signal.topic, signal.to_dict(), key=event.transaction_id)
            for signal in signals
        ))

        try:
            risk_event = await asyncio.wait_for(self.risk_scorer.evaluate(event, list(signals)), timeout=2.0)
        except Exception as exc:
            risk_event = RiskScoreEvent(
                transaction_id=event.transaction_id,
                composite_risk=0.0,
                model_name="fallback",
                component_scores={},
                feature_vector={},
                explanation=[f"Risk evaluation failed: {type(exc).__name__}"],
                threshold_block=self.settings.decision_block_threshold,
                threshold_otp=self.settings.decision_otp_threshold,
            )
        await self.broker.publish(TopicName.TXN_SCORED.value, risk_event.to_dict(), key=event.transaction_id)

        try:
            decision_event = await asyncio.wait_for(self.decision_engine.decide(event, risk_event), timeout=2.0)
        except Exception as exc:
            decision_event = DecisionEvent(
                transaction_id=event.transaction_id,
                decision=DecisionType.ALLOW,
                composite_risk=risk_event.composite_risk,
                threshold_used=0.0,
                callback_payload={},
                policy_hits=[f"DECISION_FAILED: {type(exc).__name__}"],
                component_scores={},
            )
        await self.broker.publish(TopicName.TXN_RESPONSE.value, decision_event.to_dict(), key=event.transaction_id)

        compliance_record = await self.compliance_logger.record(event, list(signals), risk_event, decision_event)
        await self.broker.publish(TopicName.TXN_RESPONSE.value, compliance_record.to_dict(), key=event.transaction_id)

        return NetworkRunResult(
            transaction=event.to_dict(),
            signals={signal.agent_name: signal.to_dict() for signal in signals},
            risk=risk_event.to_dict(),
            decision=decision_event.to_dict(),
            compliance=compliance_record.to_dict(),
            topics={
                TopicName.TXN_RAW.value: self.broker.history(TopicName.TXN_RAW.value),
                TopicName.TXN_SCORED.value: self.broker.history(TopicName.TXN_SCORED.value),
                TopicName.TXN_ALERT.value: self.broker.history(TopicName.TXN_ALERT.value),
                TopicName.TXN_RESPONSE.value: self.broker.history(TopicName.TXN_RESPONSE.value),
            },
            orchestration_engine=self.orchestration_engine,
        )

    async def run_proof_of_concept(self) -> dict[str, Any]:
        event = self.data_strategy.proof_of_concept_event()
        result = await self.process_event(event)
        risk = result.risk["composite_risk"]
        decision = result.decision["decision"]
        return {
            "scenario": {
                "step_1": "Foreign login from AE with a burner device fingerprint mismatching the trusted handset.",
                "step_2": "High-value transfer sent to a brand-new beneficiary over UPI.",
                "step_3": "Graph traversal links the beneficiary to a mule chain and shared device cluster.",
                "step_4": f"Composite XGBoost risk score computed at {risk:.2f}.",
                "step_5": f"Decision engine returns {decision} within the response path.",
                "step_6": "Compliance logger persists audit, forensic, and report artefacts.",
            },
            "individual_agent_scores": result.risk["component_scores"],
            "final_composite_score": risk,
            "decision": decision,
            "decision_threshold_logic": {
                "block_if": f"score >= {self.settings.decision_block_threshold}",
                "otp_if": f"{self.settings.decision_otp_threshold} <= score < {self.settings.decision_block_threshold}",
                "allow_if": f"score < {self.settings.decision_otp_threshold}",
            },
            "network_result": result.to_dict(),
        }

    async def replay_paysim_stream(self, limit: int = 25) -> dict[str, Any]:
        self.bootstrap()
        decisions = {"BLOCK": 0, "OTP": 0, "ALLOW": 0}
        scores = []
        events, stream_source = self.data_strategy.replay_stream_events(max_rows=limit, start_index=120)
        for event in events:
            result = await self.process_event(event)
            decisions[result.decision["decision"]] += 1
            scores.append(result.risk["composite_risk"])
        return {
            "events_processed": len(events),
            "decisions": decisions,
            "avg_risk_score": float(f"{sum(scores) / max(len(scores), 1):.4f}"),
            "stream_source": stream_source,
        }

    def architecture(self) -> dict[str, Any]:
        return {
            "agents": [
                "Agent 01: Transaction Monitor",
                "Agent 02: Behaviour Analyser",
                "Agent 03: Graph Fraud Detector",
                "Agent 04: Risk Scorer",
                "Agent 05: Decision and Response Engine",
                "Agent 06: Compliance Logger",
            ],
            "topics": [topic.value for topic in TopicName],
            "orchestration_engine": self.orchestration_engine,
            "stack": {
                "event_streaming": "Apache Kafka with an in-memory broker for local simulation",
                "graph": "Neo4j in production, NetworkX fallback in tests",
                "supervised_ml": "XGBoost risk scoring with fallback gradient boosting",
                "unsupervised_ml": "Isolation Forest behaviour anomaly detection",
                "web_delivery": "FastAPI plus WebSocket dashboard",
                "api_orchestration": "MCP server for internal and AI tooling",
                "deployment": "Docker and Docker Compose",
            },
            "data_strategy": self.data_strategy.describe(),
        }
