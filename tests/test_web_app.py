from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app


def test_dashboard_root_serves_html():
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert "Fraud Shield Console" in response.text


def test_health_endpoint_is_ok():
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

import sys

def test_process_endpoint_uses_dashboard_service():
    sys.modules["api.app"].firebase_ready = False
    app = create_app()
    client = TestClient(app)

    async def fake_process(_payload):
        return {
            "transaction": {"transaction_id": "TXN-TEST"},
            "signals": {},
            "risk": {"composite_risk": 0.72, "explanation": ["demo"]},
            "decision": {"decision": "OTP"},
            "compliance": {"decision": "OTP"},
        }

    app.state.dashboard.process = fake_process

    response = client.post(
        "/api/transactions/process",
        json={
            "transaction_id": "TXN-TEST",
            "sender_account": "ACC-1",
            "receiver_account": "ACC-2",
            "amount": 2500,
        },
    )
    assert response.status_code == 200
    assert response.json()["decision"]["decision"] == "OTP"
