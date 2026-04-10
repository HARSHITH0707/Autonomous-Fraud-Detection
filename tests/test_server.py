import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.models import AgentSignal, TransactionEvent
from core.config import NetworkSettings
from mcp_server.server import describe_architecture, process_transaction, run_proof_of_concept
from agents.risk_scorer import RiskScorerAgent
from orchestration import FraudDetectionNetwork


def build_network(tmp_path: Path) -> FraudDetectionNetwork:
    settings = NetworkSettings()
    settings.output_dir = tmp_path
    settings.model_dir = ROOT / "ml_models"
    settings.data_dir = ROOT / "data"
    settings.use_neo4j = False
    return FraudDetectionNetwork(settings=settings)


def test_architecture_lists_six_agents(tmp_path):
    network = build_network(tmp_path)
    architecture = network.architecture()
    assert len(architecture["agents"]) == 6
    assert "txn.raw" in architecture["topics"]
    assert architecture["stack"]["supervised_ml"].startswith("XGBoost")


def test_proof_of_concept_blocks_transaction(tmp_path):
    network = build_network(tmp_path)
    result = asyncio.run(network.run_proof_of_concept())
    assert result["decision"] == "BLOCK"
    assert result["final_composite_score"] >= network.settings.decision_block_threshold
    assert result["individual_agent_scores"]["transaction_monitor"] > 0.4
    assert result["individual_agent_scores"]["behaviour_analyser"] > 0.4


def test_process_event_populates_topics(tmp_path):
    network = build_network(tmp_path)
    event = network.data_strategy.proof_of_concept_event()
    result = asyncio.run(network.process_event(event)).to_dict()
    assert len(result["topics"]["txn.raw"]) == 1
    assert len(result["topics"]["txn.response"]) >= 2
    assert result["signals"]["graph_fraud_detector"]["score"] > 0
    assert Path(result["compliance"]["audit_path"]).exists()


def test_graph_detector_recovers_with_in_memory_fallback(tmp_path):
    network = build_network(tmp_path)

    class FailingGraphBackend:
        def load(self, _frame):
            return None

        def inspect_transaction(self, _event):
            raise RuntimeError("neo4j auth failed")

    network.graph_backend = FailingGraphBackend()
    network.graph_detector.graph_backend = network.graph_backend

    event = network.data_strategy.proof_of_concept_event()
    result = asyncio.run(network.process_event(event)).to_dict()

    assert result["signals"]["graph_fraud_detector"]["score"] > 0
    assert not any(flag.startswith("EVAL_FAILED") for flag in result["signals"]["graph_fraud_detector"]["flags"])


def test_replay_stream_uses_synthetic_fallback_when_paysim_is_missing(tmp_path):
    network = build_network(tmp_path)
    network.settings.data_dir = tmp_path
    network.data_strategy = network.data_strategy.__class__(network.settings)

    result = asyncio.run(network.replay_paysim_stream(limit=20))

    assert result["events_processed"] == 20
    assert result["stream_source"] == "synthetic-fallback"
    assert sum(result["decisions"].values()) == 20
    assert result["avg_risk_score"] > 0


def test_mcp_helper_functions_return_expected_payloads():
    architecture = asyncio.run(describe_architecture())
    assert "data_strategy" in architecture

    poc = asyncio.run(run_proof_of_concept())
    assert poc["decision"] == "BLOCK"

    realtime = asyncio.run(
        process_transaction(
            {
                "transaction_id": "TEST-MCP-001",
                "source": "api",
                "channel": "card",
                "event_time": "2026-03-24T18:42:00+05:30",
                "sender_account": "ACC-PRIMARY",
                "receiver_account": "ACC-MULE-1",
                "amount": 92000,
                "transaction_type": "CARD",
                "device_id": "device-burner-77",
                "ip_address": "196.12.55.10",
                "login_country": "AE",
                "home_country": "IN",
                "device_mismatch": True,
                "geo_velocity_km": 1700,
                "new_beneficiary": True,
                "beneficiary_age_days": 0,
                "login_velocity_10m": 4,
                "recent_txn_count_5m": 5,
                "recent_amount_5m": 120000,
                "account_tenure_days": 420,
            }
        )
    )
    assert realtime["decision"]["decision"] in {"BLOCK", "OTP", "ALLOW"}
    assert realtime["risk"]["composite_risk"] >= 0


def test_risk_scorer_uses_heuristic_floor_when_model_is_too_low(tmp_path):
    scorer = RiskScorerAgent(model_dir=tmp_path, block_threshold=0.8, otp_threshold=0.55)

    class FakeLowModel:
        def predict_proba(self, _frame):
            return [[0.99, 0.01]]

    scorer.model.model = FakeLowModel()
    scorer.model.model_name = "fake-low-model"

    event = TransactionEvent(
        transaction_id="TXN-HIGH-RISK",
        source="test",
        channel="upi",
        event_time="2026-03-25T10:00:00+05:30",
        sender_account="ACC-PRIMARY",
        receiver_account="ACC-MULE-1",
        amount=185000.0,
        device_id="device-burner-77",
        ip_address="196.12.55.10",
        login_country="AE",
        home_country="IN",
        device_mismatch=True,
        geo_velocity_km=2000.0,
        new_beneficiary=True,
        beneficiary_age_days=0,
        login_velocity_10m=4,
        recent_txn_count_5m=6,
        recent_amount_5m=231000.0,
    )
    signals = [
        AgentSignal(transaction_id=event.transaction_id, agent_name="transaction_monitor", score=0.74, severity="HIGH"),
        AgentSignal(transaction_id=event.transaction_id, agent_name="behaviour_analyser", score=1.0, severity="HIGH"),
        AgentSignal(transaction_id=event.transaction_id, agent_name="graph_fraud_detector", score=0.55, severity="HIGH"),
    ]

    result = asyncio.run(scorer.evaluate(event, signals))
    assert result.composite_risk >= 0.8
    assert any("safety floor applied" in line for line in result.explanation)
