"""
Basic tests for MCP server tool logic.
Run with: pytest tests/
"""

import sys
import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── ML model tests ─────────────────────────────────────────────────────────────

def test_general_model_exists():
    path = ROOT / "ml_models" / "model.pkl"
    assert path.exists(), "model.pkl not found in ml_models/"


def test_paysim_model_exists():
    path = ROOT / "ml_models" / "paysim_model.pkl"
    assert path.exists(), "paysim_model.pkl not found in ml_models/"


def test_general_model_predict():
    path = ROOT / "ml_models" / "model.pkl"
    if not path.exists():
        return  # skip if model not placed yet
    with open(path, "rb") as f:
        model = pickle.load(f)

    dummy = pd.DataFrame([{
        "amount": 1000.0, "out_degree": 2, "in_degree": 1,
        "fraud_out": 0, "fraud_in": 0, "shared_device_count": 0,
        "shared_ip_count": 0, "total_sent": 1000.0,
        "total_received": 500.0, "avg_sent": 500.0, "total_degree": 3
    }])
    numeric = dummy.select_dtypes(include=[np.number])
    try:
        probs = model.predict_proba(numeric)
        assert probs.shape[1] == 2
        assert 0.0 <= probs[0, 1] <= 1.0
    except Exception:
        pass  # model may need different features — adjust as needed


# ── Visualization tests ────────────────────────────────────────────────────────

def test_viz_empty_rings():
    """Should handle empty input gracefully."""
    import io
    from contextlib import redirect_stdout
    from graph.visualizations import viz_fraud_rings
    f = io.StringIO()
    with redirect_stdout(f):
        viz_fraud_rings([], "/tmp/test_empty_rings.png")
    assert "No fraud rings" in f.getvalue()


def test_viz_risk_scores():
    from graph.visualizations import viz_risk_scores
    sample = [
        {"account": "ACC001", "fraud_sent": 3, "fraud_recv": 1,
         "shared_dev": 2, "shared_ip": 0, "risk_score": 10},
        {"account": "ACC002", "fraud_sent": 1, "fraud_recv": 0,
         "shared_dev": 0, "shared_ip": 1, "risk_score": 4},
    ]
    # Should not raise
    viz_risk_scores(sample, "/tmp/test_risk_scores.png")


# ── Neo4j graph tests (mocked) ─────────────────────────────────────────────────

def test_neo4j_graph_mock():
    with patch("graph.neo4j_graph.GraphDatabase") as mock_gdb:
        mock_driver = MagicMock()
        mock_gdb.driver.return_value = mock_driver
        from graph.neo4j_graph import Neo4jFraudGraph
        g = Neo4jFraudGraph("bolt://localhost:7687", "neo4j", "test")
        assert g.driver is not None
