import json
import logging
from datetime import datetime
from typing import Optional

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Agent05-DecisionEngine")

AGENT_WEIGHTS = {
    "ml_score":          0.35,
    "graph_score":       0.30,
    "behaviour_score":   0.20,
    "monitor_score":     0.15,
}

THRESHOLDS = {
    "BLOCK":         0.75,
    "OTP_CHALLENGE": 0.50,
    "ALLOW":         0.00,
}

GRAPH_RISK_MAX = 50.0


class DecisionEngine:

    def __init__(self):
        self.total_decisions = 0
        self.blocked         = 0
        self.otp_challenged  = 0
        self.allowed         = 0
        self.decision_log    = []
        log.info("DecisionEngine (Agent 05) initialized")

    def decide(self,
               transaction: dict,
               monitor_result:    Optional[dict] = None,
               behaviour_result:  Optional[dict] = None,
               ml_result:         Optional[dict] = None,
               graph_result:      Optional[dict] = None) -> dict:

        start_time = datetime.now()
        txn_id     = transaction.get("transaction_id", "UNKNOWN")
        reasoning  = []

        component_scores = {}

        ml_score = 0.5
        if ml_result:
            ml_score = ml_result.get("ensemble_fraud_score",
                       ml_result.get("general_ml_prob",
                       ml_result.get("fraud_probability", 0.5)))
            component_scores["ml_score"] = round(float(ml_score), 4)
            if ml_score > 0.7:
                reasoning.append(f"ML model flagged high fraud probability: {ml_score:.2f}")

        graph_score = 0.0
        if graph_result:
            raw_graph_risk = graph_result.get("risk_score",
                             graph_result.get("graph_risk_score", 0))
            graph_score = min(float(raw_graph_risk) / GRAPH_RISK_MAX, 1.0)
            component_scores["graph_score"] = round(graph_score, 4)
            if graph_score > 0.5:
                reasoning.append(f"Graph risk score {raw_graph_risk} — linked to fraud network")

        behaviour_score = 0.0
        if behaviour_result:
            behaviour_score = float(behaviour_result.get("behaviour_score", 0))
            component_scores["behaviour_score"] = round(behaviour_score, 4)
            if behaviour_score > 0.3:
                anomalies = behaviour_result.get("anomalies", [])
                reasoning.append(f"Behaviour anomalies: {anomalies}")

        monitor_score = 0.0
        if monitor_result:
            monitor_score = float(monitor_result.get("alert_score", 0))
            component_scores["monitor_score"] = round(monitor_score, 4)
            if monitor_score > 0.2:
                alerts = monitor_result.get("alerts", [])
                reasoning.append(f"Transaction monitor alerts: {alerts}")

        available_weight = 0.0
        weighted_sum     = 0.0

        score_map = {
            "ml_score":        ml_score,
            "graph_score":     graph_score,
            "behaviour_score": behaviour_score,
            "monitor_score":   monitor_score,
        }

        for key, score in score_map.items():
            if key in component_scores:
                weight = AGENT_WEIGHTS[key]
                weighted_sum     += score * weight
                available_weight += weight

        if available_weight > 0:
            final_score = weighted_sum / available_weight
        else:
            final_score = 0.5

        final_score = round(min(final_score, 1.0), 4)

        if final_score >= THRESHOLDS["BLOCK"]:
            action = "BLOCK"
            reasoning.append(f"DECISION: BLOCK — score {final_score:.2f} >= {THRESHOLDS['BLOCK']}")
        elif final_score >= THRESHOLDS["OTP_CHALLENGE"]:
            action = "OTP_CHALLENGE"
            reasoning.append(f"DECISION: OTP CHALLENGE — score {final_score:.2f}")
        else:
            action = "ALLOW"
            reasoning.append(f"DECISION: ALLOW — score {final_score:.2f}")

        response = self._simulate_response(action, transaction, final_score)

        end_time      = datetime.now()
        decision_ms   = int((end_time - start_time).total_seconds() * 1000)

        risk_level = "CRITICAL" if final_score >= 0.75 else \
                     "HIGH"     if final_score >= 0.50 else \
                     "MEDIUM"   if final_score >= 0.30 else "LOW"

        result = {
            "transaction_id":   txn_id,
            "action":           action,
            "final_score":      final_score,
            "risk_level":       risk_level,
            "component_scores": component_scores,
            "reasoning":        reasoning,
            "timestamp":        end_time.isoformat(),
            "decision_time_ms": decision_ms,
            "response_callback": response,
        }

        self.total_decisions += 1
        if   action == "BLOCK":         self.blocked        += 1
        elif action == "OTP_CHALLENGE": self.otp_challenged += 1
        else:                           self.allowed        += 1

        self.decision_log.append(result)

        emoji = {"BLOCK": "BLOCKED", "OTP_CHALLENGE": "OTP", "ALLOW": "ALLOWED"}[action]
        log.warning(f"[{txn_id}] {emoji} | score={final_score:.4f} | {decision_ms}ms")

        return result

    def decide_batch(self, decision_inputs: list) -> list:
        return [self.decide(**inp) for inp in decision_inputs]

    def get_stats(self) -> dict:
        total = max(self.total_decisions, 1)
        return {
            "total_decisions":  self.total_decisions,
            "blocked":          self.blocked,
            "otp_challenged":   self.otp_challenged,
            "allowed":          self.allowed,
            "block_rate":       round(self.blocked / total * 100, 2),
            "challenge_rate":   round(self.otp_challenged / total * 100, 2),
            "allow_rate":       round(self.allowed / total * 100, 2),
        }

    def get_recent_decisions(self, n: int = 10) -> list:
        return self.decision_log[-n:]

    def _simulate_response(self, action: str, transaction: dict, score: float) -> dict:
        txn_id = transaction.get("transaction_id", "UNKNOWN")
        amount = transaction.get("amount", 0)

        if action == "BLOCK":
            return {
                "status":           "BLOCKED",
                "message":          f"Transaction {txn_id} blocked due to fraud risk.",
                "amount_protected": amount,
                "action_taken":     "Payment gateway notified. Transaction declined.",
                "user_message":     "Your transaction was blocked for security reasons.",
            }
        elif action == "OTP_CHALLENGE":
            return {
                "status":       "PENDING_OTP",
                "message":      f"Transaction {txn_id} requires additional verification.",
                "action_taken": "OTP sent to registered mobile number.",
                "user_message": "Please enter the OTP to complete this transaction.",
                "otp_timeout":  "300 seconds",
            }
        else:
            return {
                "status":       "APPROVED",
                "message":      f"Transaction {txn_id} approved.",
                "action_taken": "Transaction processed normally.",
                "user_message": "Transaction successful.",
            }


if __name__ == "__main__":
    engine = DecisionEngine()
    print("\n" + "="*60)
    print("  AGENT 05 - Decision Engine Test")
    print("="*60)
    result = engine.decide(
        transaction      = {"transaction_id": "TXN_TEST", "amount": 250000},
        monitor_result   = {"alert_score": 0.75, "alerts": ["VERY_HIGH_AMOUNT"]},
        behaviour_result = {"behaviour_score": 0.80, "anomalies": ["NEW_DEVICE"]},
        ml_result        = {"ensemble_fraud_score": 0.87},
        graph_result     = {"risk_score": 45},
    )
    print(f"Action:      {result['action']}")
    print(f"Score:       {result['final_score']}")
    print(f"Risk Level:  {result['risk_level']}")
    print(f"Response:    {result['response_callback']['status']}")
    print(f"Time:        {result['decision_time_ms']}ms")
    print("\nStats:")
    print(json.dumps(engine.get_stats(), indent=2))

