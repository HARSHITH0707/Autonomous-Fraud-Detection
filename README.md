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

## Quick Start

1. Install dependencies

```bash
pip install -r requirements.txt
```

2. Copy environment defaults

```bash
cp .env.example .env
```

3. Generate graph seed data if needed

```bash
python scripts/generate_fraud_dataset.py --rows 5000
```

4. Run the proof-of-concept scenario

```bash
python scripts/run_pipeline.py --mode poc
```

5. Replay a PaySim stream

```bash
python scripts/run_pipeline.py --mode stream --limit 50
```

6. Start the browser-facing dashboard

```bash
uvicorn api.app:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

7. Start the MCP server when needed for internal tooling

```bash
python mcp_server/server.py
```

## Docker Compose

`docker-compose.yml` provisions:

- Apache Kafka
- Neo4j
- FastAPI web dashboard
- MCP server as an optional tools profile

Use:

```bash
docker compose up --build
```

Then open:

```text
http://localhost:8000
```

Optional MCP tools container:

```bash
docker compose --profile tools up --build mcp-server
```

Training and demo runs inside the same container image:

```bash
docker compose run --rm web-app python scripts/train_models.py
docker compose run --rm web-app python scripts/run_pipeline.py --mode poc --output outputs/poc.json
docker compose run --rm web-app python scripts/run_pipeline.py --mode stream --limit 50 --output outputs/stream.json
```

## Outputs

The pipeline writes:

- `outputs/compliance_log.jsonl`
- `outputs/fraud_report.csv`
- `outputs/forensics/<transaction_id>.json`

## Notes

- The local test path uses an in-memory Kafka broker and in-memory graph backend.
- The production path swaps those for Apache Kafka and Neo4j with no agent-level API change.
- XGBoost, LangGraph, and Neo4j are optional at import time so local tests can run without external services.
