"""
=============================================================================
Autonomous Fraud Detection & Response Network — MCP Server
=============================================================================
Exposes fraud detection tools via the Model Context Protocol (MCP).
Combines:
  • ML Model 1   : General fraud classifier   (model.pkl)
  • ML Model 2   : PaySim fraud classifier    (paysim_model.pkl)
  • Graph Model  : Neo4j graph pattern engine (app.py logic)

Run:
    python mcp_server/server.py
=============================================================================
"""

import json
import pickle
import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from dotenv import load_dotenv

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "ml_models"
DATA_DIR  = ROOT / "data"
OUT_DIR   = ROOT / "outputs"
OUT_DIR.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
log = logging.getLogger("fraud-mcp")

# Load local environment overrides (Neo4j connection, etc.)
load_dotenv(ROOT / ".env")

# ── load ML models ─────────────────────────────────────────────────────────────
def _load_model(name: str):
    path = MODEL_DIR / name
    if not path.exists():
        log.warning(f"Model not found: {path}")
        return None
    with open(path, "rb") as f:
        return pickle.load(f)

GENERAL_MODEL = _load_model("model.pkl")
PAYSIM_MODEL  = _load_model("paysim_model.pkl")

log.info(f"General model loaded : {GENERAL_MODEL is not None}")
log.info(f"PaySim  model loaded : {PAYSIM_MODEL  is not None}")

# ── Neo4j helper ───────────────────────────────────────────────────────────────
def _get_neo4j():
    """Lazy import so server starts even without Neo4j installed."""
    try:
        sys.path.insert(0, str(ROOT))
        from graph.neo4j_graph import Neo4jFraudGraph
        uri  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER",     "neo4j")
        pw   = os.getenv("NEO4J_PASSWORD", "frauddetection123")
        return Neo4jFraudGraph(uri, user, pw)
    except Exception as e:
        log.error(f"Neo4j unavailable: {e}")
        return None


# ── Multi-agent orchestration state ────────────────────────────────────────────
from agents import (
    TransactionMonitorAgent,
    BehaviourAnalyserAgent,
    DecisionEngine,
    ComplianceLogger,
)

MONITOR_AGENT = TransactionMonitorAgent()
BEHAVIOUR_AGENT = BehaviourAnalyserAgent()
DECISION_ENGINE = DecisionEngine()
COMPLIANCE_LOGGER = ComplianceLogger(output_dir=str(OUT_DIR))

# ── MCP server ─────────────────────────────────────────────────────────────────
app = Server("fraud-detection-server")

# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="predict_fraud_general",
            description=(
                "Run the general fraud ML classifier on one or more transactions. "
                "Returns fraud probability and label for each row."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "transactions": {
                        "type": "array",
                        "description": "List of transaction dicts with numeric feature columns.",
                        "items": {"type": "object"}
                    }
                },
                "required": ["transactions"]
            }
        ),
        Tool(
            name="predict_fraud_paysim",
            description=(
                "Run the PaySim-trained ML fraud classifier. "
                "Best for PaySim-style transaction data. "
                "Returns fraud probability and predicted label."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "transactions": {
                        "type": "array",
                        "description": "List of transaction dicts (PaySim schema).",
                        "items": {"type": "object"}
                    }
                },
                "required": ["transactions"]
            }
        ),
        Tool(
            name="run_graph_fraud_detection",
            description=(
                "Run the Neo4j graph fraud detection pipeline on a CSV file. "
                "Detects fraud rings, mule chains, coordinated hubs, and shared devices. "
                "Saves visualisation PNGs to the outputs/ directory."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "csv_path": {
                        "type": "string",
                        "description": "Absolute or relative path to the input CSV file."
                    },
                    "clear_db": {
                        "type": "boolean",
                        "description": "Whether to clear the Neo4j DB before loading. Default true.",
                        "default": True
                    }
                },
                "required": ["csv_path"]
            }
        ),
        Tool(
            name="query_fraud_patterns",
            description=(
                "Query specific fraud patterns from the Neo4j graph database. "
                "Requires the graph to be loaded first via run_graph_fraud_detection."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "enum": ["rings", "chains", "hubs", "shared_devices", "risk_scores"],
                        "description": "Which fraud pattern to query."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return. Default 10.",
                        "default": 10
                    }
                },
                "required": ["pattern"]
            }
        ),
        Tool(
            name="get_account_risk",
            description=(
                "Get the fraud risk profile of a specific account ID from the graph."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "description": "The account ID to look up."
                    }
                },
                "required": ["account_id"]
            }
        ),
        Tool(
            name="generate_visualizations",
            description=(
                "Generate all fraud visualisation PNG charts from existing Neo4j data. "
                "Saves to outputs/ directory. Run after loading graph data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "output_dir": {
                        "type": "string",
                        "description": "Directory to save PNGs. Defaults to outputs/.",
                        "default": str(OUT_DIR)
                    }
                }
            }
        ),
        Tool(
            name="load_csv_to_graph",
            description=(
                "Load a CSV transaction dataset into the Neo4j graph database "
                "without running detection queries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "csv_path": {"type": "string"},
                    "clear_db": {"type": "boolean", "default": True}
                },
                "required": ["csv_path"]
            }
        ),
        Tool(
            name="run_ensemble_prediction",
            description=(
                "Run both ML models + graph risk score on a transaction and "
                "return a combined ensemble fraud decision."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "transaction": {
                        "type": "object",
                        "description": "Single transaction dict."
                    },
                    "account_id": {
                        "type": "string",
                        "description": "Account ID to fetch graph risk score."
                    }
                },
                "required": ["transaction"]
            }
        ),
        Tool(
            name="process_transaction_autonomous",
            description=(
                "Run a full autonomous fraud workflow via MCP: transaction monitor, "
                "behaviour analysis, optional graph risk, ML ensemble, final decision, "
                "and compliance logging."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "transaction": {
                        "type": "object",
                        "description": "Single transaction dict."
                    },
                    "account_id": {
                        "type": "string",
                        "description": "Optional account ID for graph lookup. Defaults to sender_account."
                    },
                    "use_graph": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to include graph-based account risk."
                    },
                    "use_ml": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to include ML ensemble scoring."
                    }
                },
                "required": ["transaction"]
            }
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "predict_fraud_general":
            return await _predict(GENERAL_MODEL, "General", arguments)

        elif name == "predict_fraud_paysim":
            return await _predict(PAYSIM_MODEL, "PaySim", arguments)

        elif name == "run_graph_fraud_detection":
            return await _run_graph_pipeline(arguments)

        elif name == "query_fraud_patterns":
            return await _query_patterns(arguments)

        elif name == "get_account_risk":
            return await _account_risk(arguments)

        elif name == "generate_visualizations":
            return await _generate_viz(arguments)

        elif name == "load_csv_to_graph":
            return await _load_csv(arguments)

        elif name == "run_ensemble_prediction":
            return await _ensemble(arguments)

        elif name == "process_transaction_autonomous":
            return await _process_transaction_autonomous(arguments)

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        log.exception(f"Tool {name} failed")
        return [TextContent(type="text", text=f"ERROR in {name}: {e}")]


# ── helpers ───────────────────────────────────────────────────────────────────

async def _predict(model, label: str, arguments: dict) -> list[TextContent]:
    if model is None:
        return [TextContent(type="text", text=f"{label} model not loaded. Check ml_models/ directory.")]

    txns = arguments["transactions"]
    df   = pd.DataFrame(txns)

    # Keep only numeric columns. If the model doesn't carry feature names (common
    # with some estimators), we must match the expected feature count.
    numeric_df = df.select_dtypes(include=[np.number]).copy()

    try:
        expected_n = getattr(model, "n_features_in_", None)
        if expected_n is not None and numeric_df.shape[1] != expected_n:
            return [TextContent(
                type="text",
                text=(
                    f"Prediction error ({label}): Feature shape mismatch, "
                    f"expected: {expected_n}, got {numeric_df.shape[1]}. "
                    f"Provide exactly {expected_n} numeric features."
                ),
            )]
        probs  = model.predict_proba(numeric_df)[:, 1].tolist()
        labels = model.predict(numeric_df).tolist()
    except Exception as e:
        return [TextContent(type="text", text=f"Prediction error ({label}): {e}")]

    results = [
        {"transaction_index": i, "fraud_probability": round(p, 4), "predicted_label": int(l)}
        for i, (p, l) in enumerate(zip(probs, labels))
    ]
    summary = {
        "model": label,
        "total": len(results),
        "fraud_detected": sum(r["predicted_label"] for r in results),
        "results": results
    }
    return [TextContent(type="text", text=json.dumps(summary, indent=2))]


async def _run_graph_pipeline(arguments: dict) -> list[TextContent]:
    csv_path = arguments["csv_path"]
    clear_db = arguments.get("clear_db", True)

    if not Path(csv_path).exists():
        return [TextContent(type="text", text=f"CSV not found: {csv_path}")]

    g = _get_neo4j()
    if g is None:
        return [TextContent(type="text", text="Neo4j unavailable. Check connection settings.")]

    try:
        df = pd.read_csv(csv_path, parse_dates=["timestamp"])
        if clear_db:
            g.clear()
        g.setup_schema()
        g.load(df)

        rings   = g.query_rings()
        chains  = g.query_chains()
        hubs    = g.query_hubs()
        devices = g.query_shared_devices()
        risk    = g.query_risk_scores()

        # generate visualizations
        from graph.visualizations import (
            viz_fraud_rings, viz_mule_chains, viz_coordinated_hubs,
            viz_shared_devices, viz_risk_scores, viz_full_network
        )
        p = lambda n: str(OUT_DIR / n)
        viz_fraud_rings(rings,   p("viz_fraud_rings.png"))
        viz_mule_chains(chains,  p("viz_mule_chains.png"))
        viz_coordinated_hubs(hubs, p("viz_coordinated_hubs.png"))
        viz_shared_devices(devices, p("viz_shared_devices.png"))
        viz_risk_scores(risk,    p("viz_risk_scores.png"))
        viz_full_network(rings, chains, hubs, p("viz_full_fraud_network.png"))

        summary = {
            "status": "complete",
            "rows_loaded": len(df),
            "fraud_rows": int(df["is_fraud"].sum()),
            "fraud_rings":   len(rings),
            "mule_chains":   len(chains),
            "hubs_found":    len(hubs),
            "device_clusters": len(devices),
            "high_risk_accounts": len(risk),
            "visualizations_saved": str(OUT_DIR)
        }
        return [TextContent(type="text", text=json.dumps(summary, indent=2))]

    finally:
        g.close()


async def _query_patterns(arguments: dict) -> list[TextContent]:
    pattern = arguments["pattern"]
    limit   = arguments.get("limit", 10)
    g = _get_neo4j()
    if g is None:
        return [TextContent(type="text", text="Neo4j unavailable.")]

    try:
        query_map = {
            "rings":          g.query_rings,
            "chains":         g.query_chains,
            "hubs":           g.query_hubs,
            "shared_devices": g.query_shared_devices,
            "risk_scores":    g.query_risk_scores,
        }
        results = query_map[pattern]()[:limit]
        return [TextContent(type="text", text=json.dumps({"pattern": pattern, "results": results}, indent=2))]
    finally:
        g.close()


async def _account_risk(arguments: dict) -> list[TextContent]:
    account_id = arguments["account_id"]
    g = _get_neo4j()
    if g is None:
        return [TextContent(type="text", text="Neo4j unavailable.")]
    try:
        rows = g.run("""
            MATCH (a:Account {account_id: $aid})
            OPTIONAL MATCH (a)-[o:SENT_TO {is_fraud:1}]->()
            OPTIONAL MATCH ()-[i:SENT_TO  {is_fraud:1}]->(a)
            OPTIONAL MATCH (a)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(:Account)
            OPTIONAL MATCH (a)-[:USED_IP   ]->(ip:IP   )<-[:USED_IP   ]-(:Account)
            WITH a.account_id AS account,
                 count(DISTINCT o)  AS fraud_sent,
                 count(DISTINCT i)  AS fraud_recv,
                 count(DISTINCT d)  AS shared_dev,
                 count(DISTINCT ip) AS shared_ip
            RETURN account, fraud_sent, fraud_recv, shared_dev, shared_ip,
                   (fraud_sent*2 + fraud_recv + shared_dev*3 + shared_ip*2) AS risk_score
        """, {"aid": account_id})
        result = rows[0] if rows else {"account": account_id, "message": "Account not found"}
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        g.close()


async def _generate_viz(arguments: dict) -> list[TextContent]:
    out = Path(arguments.get("output_dir", str(OUT_DIR)))
    out.mkdir(exist_ok=True)
    g = _get_neo4j()
    if g is None:
        return [TextContent(type="text", text="Neo4j unavailable.")]
    try:
        rings   = g.query_rings()
        chains  = g.query_chains()
        hubs    = g.query_hubs()
        devices = g.query_shared_devices()
        risk    = g.query_risk_scores()

        from graph.visualizations import (
            viz_fraud_rings, viz_mule_chains, viz_coordinated_hubs,
            viz_shared_devices, viz_risk_scores, viz_full_network
        )
        p = lambda n: str(out / n)
        viz_fraud_rings(rings,   p("viz_fraud_rings.png"))
        viz_mule_chains(chains,  p("viz_mule_chains.png"))
        viz_coordinated_hubs(hubs, p("viz_coordinated_hubs.png"))
        viz_shared_devices(devices, p("viz_shared_devices.png"))
        viz_risk_scores(risk,    p("viz_risk_scores.png"))
        viz_full_network(rings, chains, hubs, p("viz_full_fraud_network.png"))

        return [TextContent(type="text", text=json.dumps({
            "status": "done",
            "files": [str(f) for f in out.glob("viz_*.png")]
        }, indent=2))]
    finally:
        g.close()


async def _load_csv(arguments: dict) -> list[TextContent]:
    csv_path = arguments["csv_path"]
    clear_db = arguments.get("clear_db", True)
    if not Path(csv_path).exists():
        return [TextContent(type="text", text=f"CSV not found: {csv_path}")]
    g = _get_neo4j()
    if g is None:
        return [TextContent(type="text", text="Neo4j unavailable.")]
    try:
        df = pd.read_csv(csv_path, parse_dates=["timestamp"])
        if clear_db:
            g.clear()
        g.setup_schema()
        g.load(df)
        return [TextContent(type="text", text=json.dumps({
            "status": "loaded",
            "rows": len(df),
            "fraud_rows": int(df["is_fraud"].sum())
        }, indent=2))]
    finally:
        g.close()


async def _ensemble(arguments: dict) -> list[TextContent]:
    txn        = arguments["transaction"]
    account_id = arguments.get("account_id")

    df = pd.DataFrame([txn])
    numeric_df = df.select_dtypes(include=[np.number])

    scores = {}

    # ML Model 1
    if GENERAL_MODEL:
        try:
            scores["general_ml_prob"] = round(float(GENERAL_MODEL.predict_proba(numeric_df)[0, 1]), 4)
        except Exception as e:
            scores["general_ml_error"] = str(e)

    # ML Model 2
    if PAYSIM_MODEL:
        try:
            scores["paysim_ml_prob"] = round(float(PAYSIM_MODEL.predict_proba(numeric_df)[0, 1]), 4)
        except Exception as e:
            scores["paysim_ml_error"] = str(e)

    # Graph risk
    graph_risk = 0
    if account_id:
        g = _get_neo4j()
        if g:
            try:
                rows = g.run(
                    "MATCH (a:Account {account_id: $aid}) "
                    "OPTIONAL MATCH (a)-[o:SENT_TO {is_fraud:1}]->() "
                    "WITH a, count(DISTINCT o) AS fs "
                    "RETURN (fs*2) AS risk_score",
                    {"aid": account_id}
                )
                graph_risk = rows[0]["risk_score"] if rows else 0
                scores["graph_risk_score"] = graph_risk
            finally:
                g.close()

    # Ensemble decision
    ml_probs = [v for k, v in scores.items() if k.endswith("_prob")]
    avg_prob  = float(np.mean(ml_probs)) if ml_probs else 0.5
    graph_boost = min(graph_risk / 20.0, 0.5)
    ensemble_score = min(avg_prob + graph_boost * 0.3, 1.0)

    scores["ensemble_fraud_score"] = round(ensemble_score, 4)
    scores["verdict"] = "FRAUD" if ensemble_score >= 0.5 else "LEGITIMATE"

    return [TextContent(type="text", text=json.dumps(scores, indent=2))]


async def _process_transaction_autonomous(arguments: dict) -> list[TextContent]:
    txn = arguments["transaction"]
    use_graph = arguments.get("use_graph", True)
    use_ml = arguments.get("use_ml", True)

    txn_id = txn.get("transaction_id", "UNKNOWN")
    sender_account = txn.get("sender_account")
    account_id = arguments.get("account_id") or sender_account

    # Agent 01: Transaction monitor
    monitor_result = MONITOR_AGENT.analyze(txn)

    # Agent 02: Behaviour analyser (stateful profile-based)
    behaviour_result = BEHAVIOUR_AGENT.analyze(txn)

    # ML ensemble (optional)
    ml_result = {}
    if use_ml:
        ml_text = (await _ensemble({"transaction": txn, "account_id": account_id}))[0].text
        try:
            ml_result = json.loads(ml_text)
        except Exception:
            ml_result = {"ensemble_error": ml_text}

    # Graph risk (optional)
    graph_result = {}
    if use_graph and account_id:
        graph_text = (await _account_risk({"account_id": account_id}))[0].text
        try:
            graph_result = json.loads(graph_text)
        except Exception:
            graph_result = {"graph_error": graph_text}

    # Agent 05: Decision engine
    decision = DECISION_ENGINE.decide(
        transaction=txn,
        monitor_result=monitor_result,
        behaviour_result=behaviour_result,
        ml_result=ml_result if use_ml else None,
        graph_result=graph_result if use_graph else None,
    )

    # Agent 06: Compliance logger
    compliance_entry = COMPLIANCE_LOGGER.log_decision(
        transaction=txn,
        decision=decision,
        monitor_result=monitor_result,
        behaviour_result=behaviour_result,
        ml_result=ml_result if use_ml else None,
        graph_result=graph_result if use_graph else None,
    )

    response = {
        "status": "processed",
        "transaction_id": txn_id,
        "account_id": account_id,
        "pipeline": {
            "monitor": monitor_result,
            "behaviour": behaviour_result,
            "ml": ml_result if use_ml else {"skipped": True},
            "graph": graph_result if use_graph else {"skipped": True},
            "decision": decision,
            "compliance": {
                "log_id": compliance_entry.get("log_id"),
                "reportable": compliance_entry.get("regulatory", {}).get("reportable", False),
                "case_reference": compliance_entry.get("regulatory", {}).get("case_reference"),
                "log_file": str(COMPLIANCE_LOGGER.log_file),
            },
        },
        "agent_stats": {
            "decision_engine": DECISION_ENGINE.get_stats(),
            "compliance": COMPLIANCE_LOGGER.get_stats(),
            "behaviour_profiles": BEHAVIOUR_AGENT.get_all_profiles_summary(),
        },
    }
    return [TextContent(type="text", text=json.dumps(response, indent=2))]


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    log.info("Starting Fraud Detection MCP Server...")
    async with stdio_server() as (r, w):
        await app.run(r, w, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
