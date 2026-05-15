# Multi-Agent Fraud Detection Network

This repository implements a modular, event-driven fraud prevention network for real-time financial transactions. It upgrades the earlier detector bundle into a six-agent architecture with Kafka-style topics, Neo4j-based graph investigation, supervised and unsupervised ML, an MCP orchestration layer, and a browser-facing FastAPI dashboard for live transaction decisions.

## System Overview

The network is organised around six independently scalable agents:

1. Agent 01: Transaction Monitor
   Detects velocity spikes, threshold breaches, round-amount patterns, and new beneficiaries from `txn.raw`.
2. Agent 02: Behaviour Analyser
   Scores device mismatch, foreign login, geo-velocity drift, and login bursts using profile rules plus Isolation Forest.
3. Agent 03: Graph Fraud Detector
   Uses Neo4j in production and a NetworkX fallback locally to identify mule chains, shared devices, fraud rings, and coordinated hubs.
4. Agent 04: Risk Scorer
   Aggregates the agent outputs into a composite risk score from `0.0` to `1.0` using XGBoost when available, with a deterministic fallback for local execution.
5. Agent 05: Decision and Response Engine
   Maps the risk score to `BLOCK`, `OTP`, or `ALLOW` and emits an API callback payload in milliseconds.
6. Agent 06: Compliance Logger
   Persists audit logs, forensic evidence, and regulatory reporting records.

All agents communicate through Kafka-style topics:

- `txn.raw`
- `txn.scored`
- `txn.alert`
- `txn.response`

## Architecture

### Input Sources

- UPI transactions
- Card transactions
- Net banking
- Crypto transactions

### Event Flow

1. Payment rails publish normalized transactions to `txn.raw`.
2. Transaction Monitor, Behaviour Analyser, and Graph Fraud Detector consume the same event independently.
3. Each agent publishes scored evidence to `txn.scored` and sends high-severity findings to `txn.alert`.
4. Risk Scorer aggregates the signals and publishes a composite risk record.
5. Decision Engine evaluates risk thresholds and publishes a response to `txn.response`.
6. Compliance Logger writes audit trails and forensic artefacts while preserving the response path.

### Orchestration

- `orchestration/langgraph_workflow.py` provides the central control plane.
- LangGraph is supported as the preferred orchestrator when installed.
- A sequential fallback is included so the system remains runnable in local environments and tests.
- `api/app.py` exposes a web API and WebSocket dashboard for browser clients.
- `mcp_server/server.py` exposes the architecture, proof-of-concept run, stream replay, graph seeding, and real-time transaction processing over MCP.

### Graph Layer

- `graph/neo4j_graph.py` contains:
  - `Neo4jFraudGraph` for production graph traversal
  - `InMemoryFraudGraph` for local execution and tests
- The graph detector finds:
  - mule chains
  - fraud rings
  - coordinated hubs
  - shared devices
  - shared IP infrastructure

## Technology Stack

- Event streaming: Apache Kafka
  High-throughput, decoupled event propagation between agents.
- Supervised ML: XGBoost
  Composite fraud scoring from labelled IEEE-CIS style features.
- Unsupervised ML: Isolation Forest
  Behaviour anomaly detection when labelled user behaviour is sparse.
- Graph database: Neo4j
  Multi-hop relationship detection across devices, IPs, mule paths, and rings.
- Agent orchestration: LangGraph
  Deterministic stateful orchestration for agent fan-out and fan-in.
- Backend runtime: Python 3.11
  Async orchestration, ML, MCP integration, and operational tooling.
- Web/API layer: FastAPI + WebSocket
  Browser-facing API and live fraud-ops dashboard for customer and analyst screens.
- Deployment: Docker and Docker Compose
  Local reproducibility and production-ready service packaging.
- API orchestration: MCP Server
  Tool-based internal control surface for fraud checks and simulations.

## Data Strategy

- IEEE-CIS Fraud Detection Dataset
  Used to train the supervised risk model for labelled fraud classification.
- PaySim Dataset
  Used to simulate real-time Kafka traffic and throughput validation.
- Synthetic Graph Data
  Used to seed fraud rings, mule chains, shared devices, and coordinated hubs in the graph layer.

The repository encapsulates this in `services/data_strategy.py`.

## Proof-of-Concept Scenario

The default scenario models the following flow:

1. Suspicious login from a foreign IP with a mismatched device fingerprint.
2. A high-value UPI transfer to a brand-new beneficiary.
3. Graph traversal links the beneficiary to a mule account chain and shared fraud device.
4. The Risk Scorer computes a composite score near `0.87` depending on the local model path.
5. The Decision Engine blocks the transaction within the response flow.
6. Compliance artefacts are written to `outputs/`.

Threshold logic:

- `BLOCK` when score `>= 0.80`
- `OTP` when score `>= 0.55` and `< 0.80`
- `ALLOW` when score `< 0.55`

## Repository Layout

```text
agents/                Six fraud agents
core/                  Shared settings and event schemas
graph/                 Neo4j and local graph backends
mcp_server/            MCP orchestration server
api/                   FastAPI application for browser/mobile clients
ml_models/             Model wrapper and model artefacts
orchestration/         LangGraph-style workflow
services/              Dataset strategy and ingestion helpers
streaming/             Kafka-compatible broker abstraction
scripts/               Pipeline runner, model training, and data generation
tests/                 Network and MCP tests
webui/                 Static dashboard assets
```

## Setup for Hackathon Testing

To enable the production-grade authentication and persistence layers, follow these steps.

### 1. Prerequisites
- **Docker & Docker Compose**
- **Python 3.11+**
- **Firebase Project**: Create a free project at [console.firebase.google.com](https://console.firebase.google.com/).

### 2. Local Environment Setup
Install the necessary Python libraries for local scripts (seeding, training):
```bash
pip install -r requirements.txt
```

### 3. Firebase Configuration
The system uses Firebase for secure JWT authentication.
1. **Frontend Config**: In Firebase Console, add a **Web App**. Copy the config values into your `.env` file (see `.env.example`).
2. **Backend Config**: Go to **Project Settings > Service accounts**, click **Generate new private key**, download the JSON, rename it to `firebase-service-account.json`, and place it in the project root.
3. **Enable Auth**: In Firebase Console, go to **Build > Authentication** and enable **Email/Password** and **Google**.

### 4. MongoDB & Persistence
MongoDB is used to store login history for "Impossible Travel" detection.
1. **Start MongoDB**: It is included in the `docker-compose.yml`.
2. **Seed History**: To test "Impossible Travel" immediately, seed the database with demo history:
   ```bash
   python scripts/generate_fraud_dataset.py --seed-mongo
   ```
3. **Database UI**: Monitor stored logins and decisions at `http://localhost:8081` (User: `admin`, Pass: `pass`).

### 5. Running the Full Stack
Use Docker Compose to launch Kafka, Neo4j, MongoDB, and the FastAPI Dashboard:
```bash
docker compose up --build
```
Then open: [http://localhost:8000](http://localhost:8000)

---

## 🚀 Hackathon "WOW" Features

### 🚩 Impossible Travel Detection
The `BehaviourAnalyserAgent` now cross-references every login against MongoDB. 
- **The Scenario**: If a user logs in from India and then from the US 10 minutes later, the system calculates the velocity. 
- **The Alert**: A high-impact animated alert will appear on the dashboard, and the transaction will be blocked based on physical impossibility.

### 🔐 Enterprise-Grade Security
- **Multi-Provider Auth**: Dashboard protected by Firebase JWT (Email & Google).
- **WebSocket Security**: Live feeds are secured via token handshakes.
- **PII Masking**: Sensitive data (Accounts, IPs) is masked automatically in all API responses.

### 📊 Performance
- **Per-Sender Locking**: The system supports high concurrency by processing transactions from different accounts in parallel.

---

## 🛠️ Troubleshooting & Security (For Teammates)

### 1. CORS & Origin Errors
If you are running the frontend on a different URL than `localhost:8000`, the API will block requests.
- **Fix**: Update `ALLOWED_ORIGINS` in your `.env` file with your teammate's URL (e.g., `ALLOWED_ORIGINS=http://my-dev-machine:8000`).

### 2. Live Feed (WebSocket) Issues
The "Live Feed" will only connect if you are **successfully logged in**. 
- If the feed stays "Connecting...", check the browser console. A `4001` error means the Firebase token was missing or expired. Simply refresh and log in again.

### 3. Monitoring MongoDB
Access the UI at `http://localhost:8081`. 
- **Account Logins**: Check this collection to see the "previous login" data that powers the Impossible Travel logic.
- **Transaction Decisions**: This is the real-time audit trail of every score and decision.

### 4. Monitoring Firebase
- Go to the **Authentication** tab in the Firebase Console to see users as they sign up. You can manually delete users here to test the "New User" flow.

---

## Repository Layout
```text
agents/                Six fraud agents (BehaviourAnalyser updated for Geo-Velocity)
core/                  Shared settings, DB services, and Geo-utils
graph/                 Neo4j and local graph backends
api/                   FastAPI application with Firebase JWT Middleware
webui/                 Premium Dashboard (HTML/CSS/JS)
scripts/               Seeding and pipeline runners
docker-compose.yml     Orchestrates Kafka, Neo4j, MongoDB, and Web-App
```

## Notes
- **Demo Mode**: If Firebase keys are missing from `.env`, the frontend will automatically switch to a "Demo Mode" for basic testing, but real JWT verification will be disabled.
- **Persistence**: Compliance logs and forensic artefacts are persisted to `outputs/` and the MongoDB `transaction_decisions` collection.
