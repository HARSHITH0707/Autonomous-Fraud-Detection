"""
Example MCP Client — Fraud Detection
=====================================
Run this to test the MCP server manually.

Usage:
    python scripts/mcp_client_example.py
"""

import asyncio
import json
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER_SCRIPT = ROOT / "mcp_server" / "server.py"
DEFAULT_CSV = ROOT / "data" / "synthetic_fraud_graph_dataset.csv"

SERVER_PARAMS = StdioServerParameters(
    command="python",
    args=[str(SERVER_SCRIPT)],
    env=None,
    cwd=str(ROOT),
)


async def main():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ── List all available tools ───────────────────────────────────
            tools = await session.list_tools()
            print("\n=== Available MCP Tools ===")
            for t in tools.tools:
                print(f"  • {t.name}: {t.description[:70]}...")

            print("\n=== Example 1: Predict with General ML Model ===")
            # This repo's bundled general model is an XGBoost classifier that expects
            # exactly 29 numeric features (it doesn't include feature names).
            xgb29_hi_risk = {f"f{i}": 0.0 for i in range(29)}
            xgb29_hi_risk.update({"f0": 15000.0, "f1": 1.0, "f2": 0.5})
            xgb29_low_risk = {f"f{i}": 0.0 for i in range(29)}
            xgb29_low_risk.update({"f0": 50.0})
            result = await session.call_tool(
                "predict_fraud_general",
                arguments={
                    "transactions": [
                        xgb29_hi_risk,
                        xgb29_low_risk,
                    ]
                }
            )
            raw = result.content[0].text
            try:
                print(json.dumps(json.loads(raw), indent=2))
            except Exception:
                print(raw)

            print("\n=== Example 2: Query fraud patterns (rings) ===")
            result = await session.call_tool(
                "query_fraud_patterns",
                arguments={"pattern": "risk_scores", "limit": 5}
            )
            print(result.content[0].text[:500])

            print("\n=== Example 3: Full pipeline on CSV ===")
            result = await session.call_tool(
                "run_graph_fraud_detection",
                arguments={
                    "csv_path": str(DEFAULT_CSV),
                    "clear_db": True
                }
            )
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
