from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import firebase_admin
from firebase_admin import auth, credentials
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.config import NetworkSettings
from core.models import TransactionEvent
from orchestration.langgraph_workflow import FraudDetectionNetwork

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "webui" / "static"

# Initialize Firebase (Optional/Bypass for Dev)
firebase_ready = False
try:
    # Look for service account key in environment or default location
    cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        firebase_ready = True
    elif os.getenv("FIREBASE_PROJECT_ID"):
        # Use Application Default Credentials
        firebase_admin.initialize_app()
        firebase_ready = True
    else:
        log.warning("Firebase credentials not found. Auth will be bypassed in DEV_MODE.")
except Exception as e:
    log.error(f"Firebase initialization failed: {e}")

class TransactionRequest(BaseModel):
    transaction_id: str = Field(default="TXN-WEB-001")
    sender_account: str = Field(default="ACC-PRIMARY")
    receiver_account: str = Field(default="ACC-MERCHANT-001")
    amount: float = Field(default=2500.0)
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

class DashboardService:
    def __init__(self, network: FraudDetectionNetwork) -> None:
        self.network = network
        self.db = network.db_service
        self._lock = asyncio.Lock()
        self._sockets: set[WebSocket] = set()

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self._sockets:
            return
        payload = json.dumps(message)
        dead = set()
        for ws in self._sockets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        self._sockets -= dead

    async def get_summary(self) -> dict[str, Any]:
        recent = await self.db.get_recent_decisions(limit=40)
        counts = {"ALLOW": 0, "OTP": 0, "BLOCK": 0}
        total_risk = 0.0
        
        # Convert MongoDB objects to JSON serializable
        formatted_recent = []
        for run in recent:
            if "_id" in run:
                run["_id"] = str(run["_id"])
            if "created_at" in run and isinstance(run["created_at"], (int, float, complex)):
                pass # Already serialized?
            elif "created_at" in run:
                run["created_at"] = run["created_at"].isoformat()
            
            decision = run.get("decision", "ALLOW")
            if isinstance(decision, dict):
                decision = decision.get("decision", "ALLOW")
            
            counts[decision] = counts.get(decision, 0) + 1
            total_risk += run.get("composite_risk", 0.0)
            formatted_recent.append(run)
            
        return {
            "counts": counts,
            "recent_total": len(recent),
            "avg_risk_score": round(total_risk / max(len(recent), 1), 4),
            "recent_runs": formatted_recent,
            "latest": formatted_recent[0] if formatted_recent else None,
        }

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = TransactionEvent(**payload)
        async with self._lock:
            result = await self.network.process_event(event)
            run_dict = result.to_dict(mask_sensitive=True)
            # Notify dashboard via websocket
            await self.broadcast({"type": "transaction_processed", "payload": run_dict})
            return run_dict


def create_app() -> FastAPI:
    app = FastAPI(title="Fraud Shield Console")
    settings = NetworkSettings()
    network = FraudDetectionNetwork(settings)
    dashboard = DashboardService(network)
    app.state.dashboard = dashboard
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Auth Dependency
    async def get_current_user(request: Request):
        if not firebase_ready:
            return {"uid": "dev-user", "email": "dev@example.com"}
            
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized")
            
        token = auth_header.split(" ")[1]
        try:
            decoded_token = auth.verify_id_token(token)
            return decoded_token
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        index_path = STATIC_DIR / "index.html"
        return index_path.read_text(encoding="utf-8")

    @app.get("/login", response_class=HTMLResponse)
    async def login():
        login_path = STATIC_DIR / "login.html"
        return login_path.read_text(encoding="utf-8")

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok", 
            "firebase": firebase_ready, 
            "mongodb": "connected",
            "neo4j": "connected" if settings.use_neo4j else "disabled"
        }

    @app.get("/api/dashboard/summary")
    async def dashboard_summary():
        return await dashboard.get_summary()

    @app.post("/api/transactions/process")
    async def process_transaction(request: TransactionRequest, user=Depends(get_current_user)):
        return await dashboard.process(request.model_dump())

    @app.post("/api/transactions/poc")
    async def run_poc(user=Depends(get_current_user)):
        result = await network.run_proof_of_concept()
        # The ComplianceLogger already handles DB storage in result.network_result
        await dashboard.broadcast({"type": "transaction_processed", "payload": result["network_result"]})
        return result

    @app.post("/api/transactions/replay")
    async def replay_stream(limit: int = 20, user=Depends(get_current_user)):
        return await network.replay_paysim_stream(limit=limit)

    @app.websocket("/ws/dashboard")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        dashboard._sockets.add(websocket)
        try:
            # Send initial snapshot
            summary = await dashboard.get_summary()
            await websocket.send_text(json.dumps({"type": "snapshot", "payload": summary}))
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            dashboard._sockets.remove(websocket)
        except Exception:
            dashboard._sockets.remove(websocket)

    return app


app = create_app()
