from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.config import NetworkSettings
from core.models import TransactionEvent
from orchestration import FraudDetectionNetwork

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "webui" / "static"


class TransactionRequest(BaseModel):
    transaction_id: str = Field(default="TXN-WEB-001")
    source: str = Field(default="web")
    channel: str = Field(default="upi")
    event_time: str | None = Field(default=None)
    sender_account: str = Field(default="ACC-PRIMARY")
    receiver_account: str = Field(default="ACC-MERCHANT-001")
    amount: float = Field(default=2500.0)
    currency: str = Field(default="INR")
    transaction_type: str = Field(default="UPI")
    device_id: str = Field(default="device-home-01")
    ip_address: str = Field(default="103.44.12.8")
    login_country: str = Field(default="IN")
    home_country: str = Field(default="IN")
    device_mismatch: bool = Field(default=False)
    geo_velocity_km: float = Field(default=0.0)
    new_beneficiary: bool = Field(default=False)
    beneficiary_age_days: int = Field(default=30)
    login_velocity_10m: int = Field(default=1)
    recent_txn_count_5m: int = Field(default=1)
    recent_amount_5m: float = Field(default=2500.0)
    account_tenure_days: int = Field(default=420)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)


class DashboardService:
    def __init__(self, settings: NetworkSettings | None = None) -> None:
        self.settings = settings or NetworkSettings()
        self.network = FraudDetectionNetwork(self.settings)
        self._bootstrapped = False
        self._lock = asyncio.Lock()
        self._connections: set[WebSocket] = set()
        self._recent_runs: deque[dict[str, Any]] = deque(maxlen=40)

    def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        self.network.bootstrap()
        self._bootstrapped = True

    def _record(self, result: dict[str, Any]) -> None:
        self._recent_runs.append(
            {
                "transaction": result["transaction"],
                "signals": result["signals"],
                "risk": result["risk"],
                "decision": result["decision"],
                "compliance": result["compliance"],
            }
        )

    def snapshot(self) -> dict[str, Any]:
        runs = list(self._recent_runs)
        counts = {"ALLOW": 0, "OTP": 0, "BLOCK": 0}
        risk_sum = 0.0
        for run in runs:
            counts[run["decision"]["decision"]] += 1
            risk_sum += run["risk"]["composite_risk"]
        return {
            "counts": counts,
            "recent_total": len(runs),
            "avg_risk_score": round(risk_sum / max(len(runs), 1), 4) if runs else 0.0,
            "latest": runs[-1] if runs else None,
            "recent_runs": runs,
        }

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        await websocket.send_json({"type": "snapshot", "payload": self.snapshot()})

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def _broadcast(self, message: dict[str, Any]) -> None:
        dead = []
        for websocket in list(self._connections):
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket)

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            self.bootstrap()
            event = TransactionEvent.from_dict(payload)
            result = (await self.network.process_event(event)).to_dict()
            self._record(result)
        await self._broadcast({"type": "transaction_processed", "payload": result})
        return result

    async def run_poc(self) -> dict[str, Any]:
        async with self._lock:
            self.bootstrap()
            event = self.network.data_strategy.proof_of_concept_event()
            event.transaction_id = f"{event.transaction_id}-{len(self._recent_runs) + 1:03d}"
            result = (await self.network.process_event(event)).to_dict()
            poc = {
                "scenario": {
                    "step_1": "Foreign login from AE with a burner device fingerprint mismatching the trusted handset.",
                    "step_2": "High-value transfer sent to a brand-new beneficiary over UPI.",
                    "step_3": "Graph traversal links the beneficiary to a mule chain and shared device cluster.",
                    "step_4": f"Composite XGBoost risk score computed at {result['risk']['composite_risk']:.2f}.",
                    "step_5": f"Decision engine returns {result['decision']['decision']} within the response path.",
                    "step_6": "Compliance logger persists audit, forensic, and report artefacts.",
                },
                "individual_agent_scores": result["risk"]["component_scores"],
                "final_composite_score": result["risk"]["composite_risk"],
                "decision": result["decision"]["decision"],
                "decision_threshold_logic": {
                    "block_if": f"score >= {self.settings.decision_block_threshold}",
                    "otp_if": f"{self.settings.decision_otp_threshold} <= score < {self.settings.decision_block_threshold}",
                    "allow_if": f"score < {self.settings.decision_otp_threshold}",
                },
                "network_result": result,
            }
            self._record(result)
        await self._broadcast({"type": "transaction_processed", "payload": result})
        return poc

    async def replay(self, limit: int) -> dict[str, Any]:
        async with self._lock:
            self.bootstrap()
            decisions = {"ALLOW": 0, "OTP": 0, "BLOCK": 0}
            scores = []
            for event in self.network.data_strategy.paysim_stream(max_rows=limit, start_index=120):
                result = (await self.network.process_event(event)).to_dict()
                self._record(result)
                decisions[result["decision"]["decision"]] += 1
                scores.append(result["risk"]["composite_risk"])
                await self._broadcast({"type": "transaction_processed", "payload": result})
            summary = {
                "events_processed": limit,
                "decisions": decisions,
                "avg_risk_score": round(sum(scores) / max(len(scores), 1), 4),
            }
        await self._broadcast({"type": "stream_summary", "payload": summary})
        return summary

    async def graph_overview(self) -> dict[str, Any]:
        self.bootstrap()
        backend = self.network.graph_backend
        return {
            "rings": backend.query_rings(limit=5),
            "chains": backend.query_chains(limit=5),
            "hubs": backend.query_hubs(limit=5),
            "shared_devices": backend.query_shared_devices(limit=5),
            "risk_scores": backend.query_risk_scores(limit=10),
        }


def create_app() -> FastAPI:
    app = FastAPI(title="Fraud Shield Console", version="1.0.0")
    app.state.dashboard = DashboardService()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/architecture")
    async def architecture() -> dict[str, Any]:
        return app.state.dashboard.network.architecture()

    @app.get("/api/dashboard/summary")
    async def summary() -> dict[str, Any]:
        return app.state.dashboard.snapshot()

    @app.get("/api/dashboard/recent")
    async def recent() -> list[dict[str, Any]]:
        return app.state.dashboard.snapshot()["recent_runs"]

    @app.get("/api/graph/overview")
    async def graph_overview() -> dict[str, Any]:
        return await app.state.dashboard.graph_overview()

    @app.post("/api/transactions/process")
    async def process_transaction(request: TransactionRequest) -> dict[str, Any]:
        payload = request.model_dump()
        if payload["event_time"] is None:
            payload.pop("event_time")
        return await app.state.dashboard.process(payload)

    @app.post("/api/transactions/poc")
    async def run_poc() -> dict[str, Any]:
        return await app.state.dashboard.run_poc()

    @app.post("/api/transactions/replay")
    async def replay_stream(request: ReplayRequest) -> dict[str, Any]:
        return await app.state.dashboard.replay(request.limit)

    @app.websocket("/ws/dashboard")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await app.state.dashboard.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            app.state.dashboard.disconnect(websocket)
        except Exception:
            app.state.dashboard.disconnect(websocket)

    @app.exception_handler(Exception)
    async def handle_exception(_, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(exc)})

    return app


app = create_app()
