# pyre-ignore-all-errors
from __future__ import annotations

import asyncio
import time

from core.models import AgentSignal, RiskScoreEvent, TransactionEvent
from ml_models.model_service import CompositeRiskModel


class RiskScorerAgent:
    """
    Agent 04: supervised risk aggregation. Uses XGBoost when available and falls
    back to a deterministic scoring policy for local tests.
    """

    def __init__(self, model_dir, block_threshold: float, otp_threshold: float) -> None:
        self.model = CompositeRiskModel(model_dir)
        self.block_threshold = block_threshold
        self.otp_threshold = otp_threshold

    async def evaluate(self, event: TransactionEvent, signals: list[AgentSignal]) -> RiskScoreEvent:
        started = time.perf_counter()
        component_scores = {signal.agent_name: round(signal.score, 4) for signal in signals}
        feature_vector = {
            "transaction_monitor": component_scores.get("transaction_monitor", 0.0),
            "behaviour_analyser": component_scores.get("behaviour_analyser", 0.0),
            "graph_fraud_detector": component_scores.get("graph_fraud_detector", 0.0),
            "amount_scaled": min(event.amount / 250_000.0, 1.0),
            "device_mismatch": 1.0 if event.device_mismatch else 0.0,
            "new_beneficiary": 1.0 if event.new_beneficiary else 0.0,
            "geo_velocity_scaled": min(event.geo_velocity_km / 2_000.0, 1.0),
            "login_velocity_scaled": min(event.login_velocity_10m / 5.0, 1.0),
        }
        score_components = await asyncio.to_thread(self.model.predict_components, feature_vector)
        score = float(score_components["final_score"])
        explanation = []
        if component_scores.get("transaction_monitor", 0.0) >= 0.45:
            explanation.append("velocity and threshold alerts elevated the transaction monitor contribution")
        if component_scores.get("behaviour_analyser", 0.0) >= 0.45:
            explanation.append("login, device, and geo anomalies elevated behaviour risk")
        if component_scores.get("graph_fraud_detector", 0.0) >= 0.45:
            explanation.append("graph traversal linked the transaction to suspicious entities")
        learned_score = score_components.get("learned_score")
        heuristic_score = float(score_components.get("heuristic_score") or 0.0)
        if learned_score is not None and score > float(learned_score):
            explanation.append(
                f"safety floor applied: heuristic risk {heuristic_score:.4f} overrode learned score {float(learned_score):.4f}"
            )
        elif learned_score is not None:
            explanation.append(f"learned model score {float(learned_score):.4f} aligned with heuristic floor {heuristic_score:.4f}")
        else:
            explanation.append(f"heuristic fallback score {heuristic_score:.4f} used because no trained model was available")
        if not explanation:
            explanation.append("composite score stayed below strong-alert thresholds")

        return RiskScoreEvent(
            transaction_id=event.transaction_id,
            composite_risk=score,
            model_name=self.model.model_name,
            component_scores=component_scores,
            feature_vector=feature_vector,
            explanation=explanation,
            threshold_block=self.block_threshold,
            threshold_otp=self.otp_threshold,
            processing_ms=int((time.perf_counter() - started) * 1000),
        )
