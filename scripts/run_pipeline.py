"""
Standalone Pipeline Runner
===========================
Runs the full fraud detection pipeline directly (without MCP).
Useful for batch processing or testing.

Usage:
    python scripts/run_pipeline.py --csv data/synthetic_fraud_graph_dataset.csv
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from graph.neo4j_graph import Neo4jFraudGraph
from graph.visualizations import (
    viz_fraud_rings, viz_mule_chains, viz_coordinated_hubs,
    viz_shared_devices, viz_risk_scores, viz_full_network
)
import pandas as pd
import os
from dotenv import load_dotenv


def run(csv_path: str, output_dir: str = None, clear: bool = True):
    out = Path(output_dir or ROOT / "outputs")
    out.mkdir(exist_ok=True)

    # Load local environment overrides (Neo4j connection, etc.)
    load_dotenv(ROOT / ".env")

    neo4j_uri = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
    neo4j_usr = os.getenv("NEO4J_USER",     "neo4j")
    neo4j_pw  = os.getenv("NEO4J_PASSWORD", "frauddetection123")

    print("=" * 60)
    print("  Fraud Detection Pipeline  (Standalone)")
    print("=" * 60)

    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    print(f"  Rows: {len(df):,}  |  Fraud: {df['is_fraud'].sum():,}")

    with Neo4jFraudGraph(neo4j_uri, neo4j_usr, neo4j_pw) as g:
        if clear:
            g.clear()
        g.setup_schema()
        g.load(df)

        print("\n[Querying fraud patterns ...]")
        rings   = g.query_rings()
        chains  = g.query_chains()
        hubs    = g.query_hubs()
        devices = g.query_shared_devices()
        risk    = g.query_risk_scores()

        print(f"  Rings: {len(rings)}  Chains: {len(chains)}  Hubs: {len(hubs)}  Devices: {len(devices)}")

        print("\n[Extracting graph features ...]")
        feat_df  = g.extract_features()
        enriched = df.merge(
            feat_df.rename(columns={"account_id": "sender_account"}),
            on="sender_account", how="left"
        )
        enriched.to_csv(out / "neo4j_enriched_fraud_dataset.csv", index=False)
        print(f"  Enriched CSV -> {out / 'neo4j_enriched_fraud_dataset.csv'}")

    print("\n[Generating visualizations ...]")
    p = lambda n: str(out / n)
    viz_fraud_rings(rings,   p("viz_fraud_rings.png"))
    viz_mule_chains(chains,  p("viz_mule_chains.png"))
    viz_coordinated_hubs(hubs, p("viz_coordinated_hubs.png"))
    viz_shared_devices(devices, p("viz_shared_devices.png"))
    viz_risk_scores(risk,    p("viz_risk_scores.png"))
    viz_full_network(rings, chains, hubs, p("viz_full_fraud_network.png"))

    print("\n" + "=" * 60)
    print("  DONE")
    print(f"  Output directory: {out}")
    print("=" * 60)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv",    required=True, help="Path to transaction CSV")
    p.add_argument("--output", default=None,  help="Output directory")
    p.add_argument("--no-clear", action="store_true", help="Don't clear Neo4j before loading")
    args = p.parse_args()
    run(args.csv, args.output, clear=not args.no_clear)
