from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER_SCRIPT = ROOT / "mcp_server" / "server.py"
GRAPH_CSV = ROOT / "data" / "synthetic_fraud_graph_dataset.csv"

SERVER_PARAMS = StdioServerParameters(
    command="python",
    args=[str(SERVER_SCRIPT)],
    cwd=str(ROOT),
)


async def main() -> None:
    async with stdio_client(SERVER_PARAMS) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            print("=== Available MCP Tools ===")
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"- {tool.name}")

            architecture = await session.call_tool("describe_architecture", arguments={})
            print("\n=== Architecture ===")
            print(architecture.content[0].text)

            if GRAPH_CSV.exists():
                seeded = await session.call_tool(
                    "seed_graph_from_csv",
                    arguments={"csv_path": str(GRAPH_CSV), "clear_existing": True},
                )
                print("\n=== Graph Seed ===")
                print(seeded.content[0].text)

            poc = await session.call_tool("run_proof_of_concept", arguments={})
            print("\n=== Proof Of Concept ===")
            print(poc.content[0].text)

            realtime = await session.call_tool(
                "process_realtime_transaction",
                arguments={
                    "transaction": {
                        "transaction_id": "MCP-DEMO-001",
                        "source": "api",
                        "channel": "net_banking",
                        "event_time": "2026-03-24T18:42:00+05:30",
                        "sender_account": "ACC-PRIMARY",
                        "receiver_account": "ACC-MULE-1",
                        "amount": 130000,
                        "transaction_type": "NET_BANKING",
                        "device_id": "device-burner-77",
                        "ip_address": "196.12.55.10",
                        "login_country": "AE",
                        "home_country": "IN",
                        "device_mismatch": True,
                        "geo_velocity_km": 1800,
                        "new_beneficiary": True,
                        "beneficiary_age_days": 0,
                        "login_velocity_10m": 4,
                        "recent_txn_count_5m": 5,
                        "recent_amount_5m": 170000,
                        "account_tenure_days": 420,
                    }
                },
            )
            print("\n=== Real-Time Transaction ===")
            print(realtime.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
