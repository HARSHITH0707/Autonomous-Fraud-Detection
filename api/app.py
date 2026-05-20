from __future__ import annotations

import asyncio
import base64
import json
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import firebase_admin
from core.config import NetworkSettings
from core.models import TransactionEvent
from orchestration import FraudDetectionNetwork
from api.database import save_transaction

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "webui" / "static"


def get_user_from_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    
    # 1. Try Firebase Admin verification
    try:
        from firebase_admin import auth as firebase_auth
        if firebase_admin._apps:
            decoded = firebase_auth.verify_id_token(token)
            return {"uid": decoded.get("uid"), "email": decoded.get("email")}
    except Exception as e:
        print(f"Firebase token verification failed, trying fallback decode: {e}")
    
    # 2. Local fallback decode
    try:
        parts = token.split('.')
        if len(parts) >= 2:
            payload_b64 = parts[1]
            payload_b64 += '=' * (4 - len(payload_b64) % 4)
            payload_json = base64.b64decode(payload_b64).decode('utf-8')
            decoded = json.loads(payload_json)
            return {"uid": decoded.get("uid") or decoded.get("user_id"), "email": decoded.get("email")}
    except Exception as e:
        print(f"Fallback decode failed: {e}")
    return None


def get_uid_from_request(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    user_info = get_user_from_token(token)
    return user_info.get("uid") if user_info else None


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
        
        # User-segmented state
        self._user_connections: dict[str, set[WebSocket]] = {}
        self._user_runs: dict[str, deque[dict[str, Any]]] = {}
        
        # Fallback/anonymous state
        self._default_connections: set[WebSocket] = set()
        self._default_runs: deque[dict[str, Any]] = deque(maxlen=40)

    def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        self.network.bootstrap()
        self._bootstrapped = True

    def get_user_runs(self, uid: str | None) -> deque[dict[str, Any]]:
        if not uid:
            return self._default_runs
            
        if uid not in self._user_runs:
            self._user_runs[uid] = deque(maxlen=40)
            try:
                from api.database import get_user_transactions
                history = get_user_transactions(uid, limit=40)
                for run in history:
                    self._user_runs[uid].append(run)
            except Exception as e:
                print(f"Error loading user transaction history for {uid}: {e}")
                
        return self._user_runs[uid]

    def _record(self, result: dict[str, Any], uid: str | None = None) -> None:
        run = {
            "transaction": result["transaction"],
            "signals": result["signals"],
            "risk": result["risk"],
            "decision": result["decision"],
            "compliance": result["compliance"],
        }
        runs = self.get_user_runs(uid)
        runs.append(run)
        save_transaction(result, uid)

    def snapshot(self, uid: str | None) -> dict[str, Any]:
        runs = list(self.get_user_runs(uid))
        counts = {"ALLOW": 0, "OTP": 0, "BLOCK": 0}
        risk_sum = 0.0
        for run in runs:
            decision_val = run.get("decision", {}).get("decision", "ALLOW")
            if decision_val in counts:
                counts[decision_val] += 1
            risk_sum += run.get("risk", {}).get("composite_risk", 0.0)
        return {
            "counts": counts,
            "recent_total": len(runs),
            "avg_risk_score": round(risk_sum / max(len(runs), 1), 4) if runs else 0.0,
            "latest": runs[-1] if runs else None,
            "recent_runs": runs,
        }

    async def connect(self, websocket: WebSocket, uid: str | None = None) -> None:
        await websocket.accept()
        if uid:
            if uid not in self._user_connections:
                self._user_connections[uid] = set()
            self._user_connections[uid].add(websocket)
        else:
            self._default_connections.add(websocket)
        await websocket.send_json({"type": "snapshot", "payload": self.snapshot(uid)})

    def disconnect(self, websocket: WebSocket, uid: str | None = None) -> None:
        if uid:
            if uid in self._user_connections:
                self._user_connections[uid].discard(websocket)
                if not self._user_connections[uid]:
                    self._user_connections.pop(uid, None)
        else:
            self._default_connections.discard(websocket)

    async def _broadcast(self, message: dict[str, Any], uid: str | None = None) -> None:
        dead = []
        connections = self._user_connections.get(uid, set()) if uid else self._default_connections
        for websocket in list(connections):
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket, uid)

    async def process(self, payload: dict[str, Any], uid: str | None = None) -> dict[str, Any]:
        async with self._lock:
            self.bootstrap()
            event = TransactionEvent.from_dict(payload)
            result = (await self.network.process_event(event)).to_dict()
            self._record(result, uid)
        await self._broadcast({"type": "transaction_processed", "payload": result}, uid)
        return result

    async def run_poc(self, uid: str | None = None) -> dict[str, Any]:
        async with self._lock:
            self.bootstrap()
            event = self.network.data_strategy.proof_of_concept_event()
            runs = self.get_user_runs(uid)
            event.transaction_id = f"{event.transaction_id}-{len(runs) + 1:03d}"
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
            self._record(result, uid)
        await self._broadcast({"type": "transaction_processed", "payload": result}, uid)
        return poc

    async def replay(self, limit: int, uid: str | None = None) -> dict[str, Any]:
        async with self._lock:
            self.bootstrap()
            decisions = {"ALLOW": 0, "OTP": 0, "BLOCK": 0}
            scores = []
            events, stream_source = self.network.data_strategy.replay_stream_events(max_rows=limit, start_index=120)
            for event in events:
                result = (await self.network.process_event(event)).to_dict()
                self._record(result, uid)
                decisions[result["decision"]["decision"]] += 1
                scores.append(result["risk"]["composite_risk"])
                await self._broadcast({"type": "transaction_processed", "payload": result}, uid)
            summary = {
                "events_processed": len(events),
                "decisions": decisions,
                "avg_risk_score": round(sum(scores) / max(len(scores), 1), 4),
                "stream_source": stream_source,
            }
        await self._broadcast({"type": "stream_summary", "payload": summary}, uid)
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

    @app.middleware("http")
    async def redirect_bind_all_host(request: Request, call_next):
        if request.url.hostname == "0.0.0.0":
            redirect_url = request.url.replace(hostname="localhost")
            return RedirectResponse(str(redirect_url), status_code=307)
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "profile.html")

    @app.get("/dashboard")
    async def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/profile")
    async def profile() -> FileResponse:
        return FileResponse(STATIC_DIR / "profile.html")

    @app.get("/about")
    async def about() -> FileResponse:
        return FileResponse(STATIC_DIR / "about.html")

    @app.get("/api/config/firebase")
    async def firebase_config() -> dict[str, str]:
        import os
        return {
            "apiKey": os.getenv("FIREBASE_API_KEY", ""),
            "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
            "projectId": os.getenv("FIREBASE_PROJECT_ID", ""),
            "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", ""),
            "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
            "appId": os.getenv("FIREBASE_APP_ID", ""),
            "measurementId": os.getenv("FIREBASE_MEASUREMENT_ID", "")
        }

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/architecture")
    async def architecture() -> dict[str, Any]:
        return app.state.dashboard.network.architecture()

    @app.get("/api/dashboard/summary")
    async def summary(request: Request) -> dict[str, Any]:
        uid = get_uid_from_request(request)
        return app.state.dashboard.snapshot(uid)

    @app.get("/api/dashboard/recent")
    async def recent(request: Request) -> list[dict[str, Any]]:
        uid = get_uid_from_request(request)
        return app.state.dashboard.snapshot(uid)["recent_runs"]

    @app.get("/api/graph/overview")
    async def graph_overview() -> dict[str, Any]:
        return await app.state.dashboard.graph_overview()

    @app.post("/api/transactions/process")
    async def process_transaction(request: Request, tx_req: TransactionRequest) -> dict[str, Any]:
        uid = get_uid_from_request(request)
        payload = tx_req.model_dump()
        if payload["event_time"] is None:
            payload.pop("event_time")
        return await app.state.dashboard.process(payload, uid)

    @app.post("/api/transactions/poc")
    async def run_poc(request: Request) -> dict[str, Any]:
        uid = get_uid_from_request(request)
        return await app.state.dashboard.run_poc(uid)

    @app.post("/api/transactions/replay")
    async def replay_stream(request: Request, replay_req: ReplayRequest) -> dict[str, Any]:
        uid = get_uid_from_request(request)
        return await app.state.dashboard.replay(replay_req.limit, uid)

    @app.websocket("/ws/dashboard")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        token = websocket.query_params.get("token")
        uid = None
        if token:
            user_info = get_user_from_token(token)
            if user_info:
                uid = user_info.get("uid")

        await app.state.dashboard.connect(websocket, uid)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            app.state.dashboard.disconnect(websocket, uid)
        except Exception:
            app.state.dashboard.disconnect(websocket, uid)

    @app.exception_handler(Exception)
    async def handle_exception(_, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(exc)})

    return app


app = create_app()
