from __future__ import annotations

import time

from core.models import DecisionEvent, DecisionType, RiskScoreEvent, TransactionEvent


class DecisionEngineAgent:
    """
    Agent 05: decision and response engine.
    """

    def __init__(self, block_threshold: float = 0.8, otp_threshold: float = 0.55) -> None:
        self.block_threshold = block_threshold
        self.otp_threshold = otp_threshold

    async def decide(self, event: TransactionEvent, risk_event: RiskScoreEvent) -> DecisionEvent:
        started = time.perf_counter()
        risk = risk_event.composite_risk
        policy_hits: list[str] = []

        if risk >= self.block_threshold:
            decision = DecisionType.BLOCK
            threshold = self.block_threshold
            policy_hits.append(f"risk>={self.block_threshold}")
        elif risk >= self.otp_threshold:
            decision = DecisionType.OTP
            threshold = self.otp_threshold
            policy_hits.append(f"risk>={self.otp_threshold}")
        else:
            decision = DecisionType.ALLOW
            threshold = 0.0

        if risk_event.component_scores.get("graph_fraud_detector", 0.0) >= 0.5:
            policy_hits.append("graph-risk")
        if risk_event.component_scores.get("behaviour_analyser", 0.0) >= 0.5:
            policy_hits.append("behaviour-anomaly")
        if risk_event.component_scores.get("transaction_monitor", 0.0) >= 0.5:
            policy_hits.append("velocity-threshold")

        callback_payload = {
            "transaction_id": event.transaction_id,
            "decision": decision.value,
            "risk_score": risk,
            "channel": event.channel,
            "api_response_ms": int((time.perf_counter() - started) * 1000),
            "recommended_action": {
                DecisionType.BLOCK: "decline_and_freeze",
                DecisionType.OTP: "step_up_authentication",
                DecisionType.ALLOW: "approve",
            }[decision],
        }
        return DecisionEvent(
            transaction_id=event.transaction_id,
            decision=decision,
            composite_risk=risk,
            threshold_used=threshold,
            callback_payload=callback_payload,
            policy_hits=policy_hits,
            component_scores=risk_event.component_scores,
            processing_ms=int((time.perf_counter() - started) * 1000),
        )
