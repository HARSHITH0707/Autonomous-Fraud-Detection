# Virtusa Jatayu S5 — Team Contribution Breakdown

## Multi-Agent Fraud Detection Network (MAFDN)

> **Strategy**: Every member owns a **core backend subsystem** (agents / ML / graph / orchestration) **+** a slice of the **frontend dashboard**. This way, in interviews, everyone can speak to both the system internals and the UI they built — no one looks like "just the frontend person."

---

## Quick Overview

| Member | Core Backend Ownership | Frontend Ownership | Infra / Cross-cutting |
|---|---|---|---|
| **Karthik** | LangGraph Orchestration Engine, Risk Scorer Agent, ML Model Service | Decision Board panel, Agent Signals panel | Docker Compose, CI pipeline |
| **Siddharth** | Graph Fraud Detector Agent, Neo4j + InMemory Graph Backends, Graph Visualizations | Graph Intel panel | Neo4j schema & data seeding |
| **Harshith** | Transaction Monitor Agent, Behaviour Analyser Agent, Kafka Streaming Broker | Transaction Console panel, Live Feed panel | Core event schemas & models |
| **Krishna** | FastAPI + WebSocket Backend, MCP Server, Decision Engine Agent | WebSocket real-time integration, Dashboard CSS/Theming | CORS, middleware, error handling |
| **Narasimha** | Compliance Logger Agent, Data Strategy Service | Hero Metrics section, Dashboard Summary rendering | Scripts (pipeline, training, data gen), Tests |

---

## 1. KARTHIK — Orchestration & Risk Intelligence Lead

### Core Backend
- **LangGraph Orchestration Engine** (`orchestration/langgraph_workflow.py`)
  - Designed and implemented the central `FraudDetectionNetwork` class — the control plane that wires all six agents into a deterministic fan-out/fan-in pipeline
  - Built the `process_event()` async pipeline: publish to `txn.raw` → parallel agent evaluation → risk aggregation → decision → compliance logging
  - Implemented **circuit breaker pattern** (`_safe_eval`) with failure counting, cooldown windows, and automatic fallback signals when agents exceed timeout thresholds
  - Built automatic graph backend fallback: if Neo4j becomes unavailable mid-pipeline, the system hot-switches to the InMemoryFraudGraph without dropping the transaction
  - Designed `NetworkRunResult` dataclass with PII masking support (account IDs, IP addresses) for safe API exposure
  - Integrated LangGraph as the preferred orchestrator with a sequential fallback so the system remains runnable without the LangGraph dependency

- **Risk Scorer Agent** — Agent 04 (`agents/risk_scorer.py`)
  - Implemented composite risk aggregation that fuses outputs from all three detection agents (Transaction Monitor, Behaviour Analyser, Graph Detector) into a single `0.0–1.0` risk score
  - Built the 8-dimensional feature vector (agent scores + transaction metadata) that feeds the XGBoost model
  - Designed the safety floor logic: the heuristic score acts as a minimum bound so a weakly calibrated ML model can never suppress obvious fraud evidence

- **ML Model Service** (`ml_models/model_service.py`)
  - Built `CompositeRiskModel` with a multi-tier strategy: XGBoost → GradientBoosting → heuristic sigmoid fallback
  - Implemented `predict_components()` which returns learned score, heuristic score, and final score with full auditability
  - Designed the heuristic scoring function: a weighted sigmoid over agent scores and transaction features, hand-tuned against the IEEE-CIS fraud distribution
  - Built model persistence with joblib serialization and metadata tracking

### Frontend
- **Decision Board panel** (`webui/static/index.html` lines 60–75, `dashboard.js` → `renderLatest()`)
  - Built the real-time decision banner that dynamically changes color and label based on BLOCK/OTP/ALLOW outcomes
  - Implemented the composite risk score display and threshold outcome visualization
  - Built the decision distribution grid (ALLOW/OTP/BLOCK counters)
  - Implemented the reason-pill rendering that surfaces risk explanations from the backend

- **Agent Signals panel** (`webui/static/index.html` lines 77–83, `dashboard.js` → agent card rendering)
  - Built dynamic agent score cards showing per-agent score, severity level, progress bar, and flag chips
  - Cards are generated from the `signals` map in the API response — each card visualizes one agent's contribution to the final decision

### Infrastructure
- Docker Compose multi-service orchestration (`docker-compose.yml`) — Kafka, Neo4j, FastAPI web app, and MCP server as an optional tools profile
- Environment configuration and settings management (`core/config.py`)

### 📋 Ready-to-Paste Form Response (Karthik)
> I designed and implemented the **LangGraph-based orchestration engine** — the central control plane that coordinates all six fraud detection agents in a deterministic fan-out/fan-in pipeline. I built the `FraudDetectionNetwork` class which manages the full async transaction processing lifecycle: publishing to Kafka topics, running three detection agents in parallel using `asyncio.gather`, aggregating their signals through the Risk Scorer, and routing decisions through the Decision Engine. I implemented a **circuit breaker pattern** with failure counting and cooldown windows so individual agent failures degrade gracefully without dropping transactions. I also built automatic **Neo4j-to-InMemory graph failover** for production resilience. On the ML side, I implemented the **Risk Scorer Agent (Agent 04)** and the **CompositeRiskModel** which fuses XGBoost-learned probabilities with a hand-tuned heuristic sigmoid, enforcing a safety floor so weak model calibration can never suppress strong fraud evidence. On the frontend, I built the **Decision Board** and **Agent Signals** panels of the live dashboard — including the real-time decision banner, composite risk display, per-agent score cards with severity bars, and the risk explanation pill renderer. I also set up the **Docker Compose** multi-service infrastructure for Kafka, Neo4j, and the web application.

---

## 2. SIDDHARTH — Graph Intelligence & Fraud Network Analysis Lead

### Core Backend
- **Graph Fraud Detector Agent** — Agent 03 (`agents/graph_fraud_detector.py`)
  - Implemented the agent that bridges real-time transaction evaluation with the graph layer
  - Calls `inspect_transaction()` on the graph backend for every incoming event and translates graph evidence (shared devices, mule chains, fraud rings) into scored `AgentSignal` objects

- **Neo4j Graph Backend** (`graph/neo4j_graph.py` → `Neo4jFraudGraph`)
  - Built the production Neo4j integration with Cypher queries for:
    - **Fraud ring detection** — variable-length path traversal (`*3..4`) with fraud-edge filtering to find cyclic money laundering loops
    - **Mule chain detection** — acyclic path traversal (`*3..5`) with uniqueness constraints to identify layered fund movement
    - **Coordinated hub identification** — aggregation of distinct fraud senders into high-in-degree receiver nodes
    - **Shared device/IP clustering** — bipartite graph queries linking accounts through device and IP infrastructure
  - Implemented `inspect_transaction()` with targeted Cypher: per-transaction graph lookups for real-time scoring against shared devices, mule chains, fraud rings, and hub connectivity
  - Built schema setup with uniqueness constraints on Account, Device, and IP nodes
  - Implemented batched graph loading (`BATCH_SIZE=500`) with `UNWIND` for efficient bulk ingestion
  - Added retry logic with configurable delays for transient Neo4j failures

- **InMemory Graph Backend** (`graph/neo4j_graph.py` → `InMemoryFraudGraph`)
  - Built a pure-Python graph backend (no NetworkX dependency) using adjacency lists, providing the same API surface as the Neo4j backend
  - Implemented DFS-based ring detection with canonical cycle normalization to deduplicate rotated rings
  - Implemented chain walking with hop-bounded recursion for mule chain detection
  - Built shared-device and shared-IP indexing with inverted mappings for O(1) lookups
  - Implemented `extract_features()` for graph-level feature engineering (degree, fraud in/out, shared device/IP counts)

- **Graph Visualizations** (`graph/visualizations.py`)
  - Built matplotlib + NetworkX visualization suite:
    - Fraud ring rendering with circular layouts
    - Mule chain rendering with linear hop layouts and color-coded source/destination
    - Coordinated hub rendering with shell layouts
    - Shared device cluster rendering
    - Combined full-network overview with spring layout and legend
  - Dark-themed styling (DARK/PANEL/FRAUD/HUB color palette) for dashboard-consistent output

### Frontend
- **Graph Intel panel** (`webui/static/index.html` lines 93–99, `dashboard.js` → `renderGraphOverview()`)
  - Built the graph intelligence section that displays fraud rings, mule chains, coordinated hubs, and shared device clusters pulled from the `/api/graph/overview` endpoint
  - Each category renders as a graph card with formatted evidence (member chains, hop counts, sender counts, linked accounts)

### Infrastructure
- Neo4j Docker service configuration and schema bootstrapping
- Graph data seeding from CSV via the MCP `seed_graph_from_csv` tool

### 📋 Ready-to-Paste Form Response (Siddharth)
> I designed and implemented the **Graph Intelligence subsystem** — the core differentiator that enables relationship-based fraud detection beyond isolated transaction scoring. I built both the **production Neo4j backend** and the **InMemory fallback graph backend**, each exposing the same API surface so the system runs identically in production and local testing environments. For Neo4j, I wrote optimized **Cypher queries** for fraud ring detection (variable-length cyclic path traversal), mule chain discovery (acyclic bounded-hop walks), coordinated hub identification (high-in-degree aggregation), and shared device/IP clustering (bipartite graph queries). I implemented **batched graph ingestion** with `UNWIND` for efficient bulk loading and **retry logic** for transient database failures. The InMemory backend uses pure-Python adjacency lists with DFS-based ring detection and canonical cycle normalization to deduplicate rotated rings. I also built the **Graph Fraud Detector Agent (Agent 03)** which performs real-time per-transaction graph lookups during the pipeline. On the visualization side, I built the **matplotlib + NetworkX rendering suite** for fraud rings, mule chains, hubs, and shared devices with a dark-themed color palette. On the frontend, I implemented the **Graph Intel panel** that surfaces fraud structures (rings, chains, hubs, shared devices) in the live dashboard.

---

## 3. HARSHITH — Transaction Analysis & Real-Time Streaming Lead

### Core Backend
- **Transaction Monitor Agent** — Agent 01 (`agents/transaction_monitor.py`)
  - Implemented velocity spike detection using a sliding 5-minute window with per-sender LRU-cached transaction deques
  - Built multi-signal scoring: amount thresholds (₹75K/₹200K bands), velocity count (≥5 txns/5min), velocity amount (≥₹100K rolling), new beneficiary detection, high-risk rail identification (CRYPTO/CASH_OUT), and round-amount mule batching patterns
  - Designed severity mapping (LOW/MEDIUM/HIGH) and topic routing (scored vs. alert) based on score thresholds
  - Implemented evidence collection with per-transaction forensic context (recent counts, amounts, account pairs)

- **Behaviour Analyser Agent** — Agent 02 (`agents/behaviour_analyser.py`)
  - Built profile-based anomaly detection using `BehaviourProfile` dataclass: tracks per-account countries, devices, amounts, and IP prefixes
  - Implemented rule-based checks: foreign login, device mismatch, new device/geography, impossible travel (≥900km geo-velocity), amount spike (z-score ≥3.0), and login burst detection
  - Integrated **scikit-learn Isolation Forest** for unsupervised behaviour anomaly scoring — the model trains on bootstrap history and flags sessions that fall outside the learned distribution
  - Built `bootstrap()` to pre-train the Isolation Forest on historical transaction vectors during system initialization

- **Kafka-Style Streaming Broker** (`streaming/broker.py`)
  - Implemented `InMemoryKafkaBroker` — a Kafka-compatible topic-based message broker for local simulation
  - Supports `publish()` with key-based routing and `history()` for topic replay
  - Designed to be API-compatible with the production Kafka path so the swap requires no agent-level code changes

### Frontend
- **Transaction Console panel** (`webui/static/index.html` lines 30–57, `dashboard.js` → `readTransactionForm()`, form submit handler)
  - Built the main transaction input form with 15+ fields covering transaction details, device/geo context, and risk indicators
  - Implemented `readTransactionForm()` which serializes form data into the API request payload
  - Built the three action buttons: "Process Transaction" (form submit → `/api/transactions/process`), "Run Suspicious PoC" (→ `/api/transactions/poc`), and "Replay 20-Event Stream" (→ `/api/transactions/replay`)

- **Live Feed panel** (`webui/static/index.html` lines 85–91, `dashboard.js` → `renderFeed()`)
  - Built the real-time transaction feed that displays recent decisions in reverse chronological order
  - Each feed item shows transaction ID, sender→receiver flow, channel, amount, risk score, and a color-coded decision chip (ALLOW/OTP/BLOCK)
  - Feed items are clickable — selecting one re-renders the Decision Board with that transaction's full details

### Core Schemas
- **Event Models** (`core/models.py`) — `TransactionEvent`, `AgentSignal`, `RiskScoreEvent`, `DecisionEvent`, `ComplianceRecord` dataclasses with serialization and Kafka topic enums

### 📋 Ready-to-Paste Form Response (Harshith)
> I implemented the two primary detection agents in the fraud pipeline. The **Transaction Monitor (Agent 01)** performs real-time velocity analysis using a sliding 5-minute window with per-sender LRU-cached transaction deques. It scores across six signals: amount threshold breaches (₹75K/₹200K bands), velocity count and amount spikes, new beneficiary detection, high-risk payment rail identification (CRYPTO/CASH_OUT), and round-amount mule batching patterns. The **Behaviour Analyser (Agent 02)** maintains per-account `BehaviourProfile` objects tracking historical countries, devices, amounts, and IP prefixes, then detects anomalies like foreign login, device mismatch, impossible travel (geo-velocity ≥900km), amount z-score spikes, and login bursts. I also integrated **scikit-learn's Isolation Forest** for unsupervised anomaly scoring that trains on bootstrap history. Additionally, I built the **Kafka-style streaming broker** — an in-memory topic-based message bus that mirrors the Kafka API so production and local simulation run with zero code changes. I also defined the **core event schemas** (TransactionEvent, AgentSignal, RiskScoreEvent, DecisionEvent) used by all agents. On the frontend, I built the **Transaction Console** with 15+ input fields, three action buttons (Process/PoC/Replay), and the **Live Feed panel** showing real-time decisions with clickable items that drill into full transaction details.

---

## 4. KRISHNA — API Platform & Real-Time Communication Lead

### Core Backend
- **FastAPI Backend & WebSocket Layer** (`api/app.py`)
  - Designed and implemented the `DashboardService` class — the service layer that manages network bootstrapping, async locking, connection pools, and recent-run history
  - Built the full REST API surface:
    - `GET /api/health` — service health check
    - `GET /api/architecture` — returns the six-agent architecture, tech stack, and data strategy
    - `GET /api/dashboard/summary` — aggregated dashboard snapshot with decision counts and average risk
    - `GET /api/dashboard/recent` — recent transaction runs
    - `GET /api/graph/overview` — graph intelligence data (rings, chains, hubs, devices)
    - `POST /api/transactions/process` — full pipeline execution for a single transaction
    - `POST /api/transactions/poc` — proof-of-concept scenario runner
    - `POST /api/transactions/replay` — PaySim stream replay
  - Implemented **WebSocket endpoint** (`/ws/dashboard`) with connection lifecycle management, automatic dead connection pruning, and broadcast to all connected dashboard clients
  - Built `process()` with async locking to serialize pipeline execution and broadcast results to all WebSocket subscribers
  - Implemented the PoC runner with stepped scenario descriptions and comprehensive threshold logic output

- **MCP Server** (`mcp_server/server.py`)
  - Built the Model Context Protocol server exposing 5 tools for AI agent integration:
    - `describe_architecture` — returns full network architecture and tech stack
    - `process_realtime_transaction` — runs a transaction through the full pipeline
    - `run_proof_of_concept` — executes the suspicious-login scenario
    - `replay_paysim_stream` — replays PaySim events for throughput testing
    - `seed_graph_from_csv` — seeds the graph backend from CSV data
  - Implemented MCP fallback stubs so the server gracefully degrades when the `mcp` package is not installed

- **Decision Engine Agent** — Agent 05 (`agents/decision_engine.py`)
  - Implemented the threshold-based decision mapper: BLOCK (≥0.80), OTP (≥0.55), ALLOW (<0.55)
  - Built the API callback payload generator with decision metadata, policy hits, and component scores

### Frontend
- **WebSocket Integration** (`dashboard.js` → `init()`, WebSocket message handlers)
  - Built the client-side WebSocket connection with protocol detection (ws/wss) and message routing
  - Implemented `snapshot` and `transaction_processed` message handlers that update all dashboard panels in real time
  - Built client-side aggregation: decision counting, risk averaging, and recent-runs buffer management (capped at 40 entries)

- **Dashboard CSS & Theming** (`webui/static/dashboard.css`)
  - Designed the full dashboard visual system: dark theme, glassmorphism panels, responsive grid layout
  - Built the decision banner color states (BLOCK=red, OTP=amber, ALLOW=green, neutral=gray)
  - Styled agent cards, stat cards, metric cards, graph cards, decision chips, reason pills, and flag badges
  - Implemented responsive breakpoints and hover interactions

### Infrastructure
- CORS middleware configuration, static file serving, and global exception handler

### 📋 Ready-to-Paste Form Response (Krishna)
> I designed and implemented the **FastAPI backend platform** and the **real-time WebSocket communication layer** that powers the live fraud dashboard. I built the `DashboardService` class which manages network bootstrapping, async locking for serialized pipeline execution, WebSocket connection pools with automatic dead-connection pruning, and recent-run history tracking. The REST API exposes 8 endpoints covering health checks, architecture introspection, dashboard summaries, graph intelligence, transaction processing, PoC execution, and PaySim stream replay. The **WebSocket endpoint** (`/ws/dashboard`) broadcasts every pipeline result to all connected dashboard clients in real time. I also built the **MCP Server** — a Model Context Protocol integration that exposes 5 tools (architecture, transaction processing, PoC, stream replay, graph seeding) for AI agent orchestration, with graceful fallback stubs when the MCP package is unavailable. I implemented the **Decision Engine (Agent 05)** with configurable threshold logic (BLOCK ≥0.80, OTP ≥0.55, ALLOW <0.55) and API callback payload generation. On the frontend, I built the **WebSocket client integration** with protocol detection and message routing, and designed the entire **dashboard CSS** — dark theme, glassmorphism panels, responsive grid, color-coded decision banners, and micro-animated agent/stat/graph cards.

---

## 5. NARASIMHA — Data Pipeline & Compliance Lead

### Core Backend
- **Compliance Logger Agent** — Agent 06 (`agents/compliance_logger.py`)
  - Implemented audit trail persistence: writes structured compliance records after every pipeline decision
  - Built forensic evidence packaging — captures agent signals, risk scores, and decision metadata into per-transaction forensic JSON files
  - Implemented regulatory report generation writing to `outputs/compliance_log.jsonl` and `outputs/fraud_report.csv`

- **Data Strategy Service** (`services/data_strategy.py`)
  - Built the unified `DataStrategy` class managing three data sources:
    - **IEEE-CIS loading**: reads `train_transaction.csv` and `train_identity.csv`, merges on `TransactionID`, and engineers 8 features for XGBoost training (amount scaling, device mismatch, geo velocity, percentile-ranked card features)
    - **PaySim streaming**: converts PaySim CSV rows into `TransactionEvent` objects with fraud-conditioned enrichment (foreign login injection, device mismatch, geo velocity, mule routing)
    - **Synthetic graph seed**: loads fraud graph CSVs with deduplication, ensures default mule-chain and ring structures are always present
  - Built `bootstrap_history()` for Isolation Forest pre-training with real or synthetic event sequences
  - Designed `proof_of_concept_event()` — the carefully tuned PoC transaction that triggers all six agents across every detection dimension
  - Implemented synthetic replay stream fallback with three risk bands (high/medium/low) for environments without PaySim data

### Frontend
- **Hero Metrics section** (`webui/static/index.html` lines 17–26, `dashboard.js` → `renderSummary()`)
  - Built the top-level metrics bar showing "Recent Decisions" count and "Average Risk" score
  - Metrics update in real time from both REST polling and WebSocket push

- **Dashboard Summary rendering** (`dashboard.js` → `renderSummary()`)
  - Implemented the summary renderer that updates all counter elements, average risk display, and triggers feed + latest-decision re-renders on every new data snapshot

### Scripts & Testing
- **Pipeline Runner** (`scripts/run_pipeline.py`) — CLI for PoC and stream replay modes with JSON output
- **Model Training** (`scripts/train_models.py`) — trains and persists the XGBoost risk model from IEEE-CIS data
- **Dataset Generation** (`scripts/generate_fraud_dataset.py`) — generates synthetic fraud graph datasets with configurable row counts for ring, chain, hub, and shared-device structures
- **Test Suite** (`tests/test_server.py`, `tests/test_web_app.py`) — MCP server tool tests and FastAPI endpoint tests

### 📋 Ready-to-Paste Form Response (Narasimha)
> I implemented the **Compliance Logger (Agent 06)** which handles audit trail persistence, forensic evidence packaging, and regulatory report generation — writing structured compliance records, per-transaction forensic JSON, and report-ready CSVs to the outputs directory after every pipeline decision. I also built the **Data Strategy Service** — the unified data management layer that handles three distinct data sources: **IEEE-CIS** dataset loading with feature engineering (merging transaction and identity tables, computing scaled features for XGBoost), **PaySim** stream conversion (transforming CSV rows into enriched `TransactionEvent` objects with fraud-conditioned signals like foreign login injection and mule routing), and **synthetic graph seeding** (loading fraud graph CSVs with deduplication and default structure guarantees). I designed the **proof-of-concept event** — a carefully tuned suspicious transaction that triggers all six detection agents across every dimension. I built the **synthetic replay fallback** with three risk bands for environments without real data. On the frontend, I implemented the **Hero Metrics bar** (real-time decision counts and average risk score) and the **Dashboard Summary renderer** that updates all counters and triggers panel re-renders on new data. I also built the **CLI scripts** for pipeline execution, XGBoost model training, and synthetic dataset generation, and wrote the **test suite** covering MCP server tools and FastAPI endpoints.

---

## Interview Prep Tips

> [!TIP]
> **For everyone**: When asked "What did you work on?", lead with your **core agent/system** responsibility, then mention the frontend panel you built. This shows you're full-stack and understand the entire pipeline.

> [!IMPORTANT]
> **Key talking points every member should know:**
> - The system uses a **fan-out/fan-in architecture** — three detection agents run in parallel, their signals are aggregated by the Risk Scorer
> - Communication happens through **Kafka-style topics** (`txn.raw`, `txn.scored`, `txn.alert`, `txn.response`)
> - The decision logic uses **configurable thresholds**: BLOCK ≥0.80, OTP ≥0.55, ALLOW <0.55
> - The graph layer has **production (Neo4j) and local (InMemory) backends** with the same API surface
> - The ML model uses a **safety floor**: `max(learned_score, heuristic_score)` so weak calibration can't suppress obvious fraud
> - The frontend dashboard updates in **real time via WebSocket** — not polling

> [!WARNING]
> **Make sure each person can explain their specific files and logic.** If the interviewer asks Siddharth about Cypher queries, he should be able to talk about variable-length path traversal. If they ask Harshith about the Isolation Forest, he should know it uses `contamination=0.04` and trains on 7-dimensional behaviour vectors.
