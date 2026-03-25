# pyre-ignore-all-errors
from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.compat import load_dotenv, optional_import, read_csv_records
from core.config import NetworkSettings
from core.models import TransactionEvent
from orchestration import FraudDetectionNetwork

pd = optional_import("pandas")

_mcp_server = optional_import("mcp.server")
_mcp_stdio = optional_import("mcp.server.stdio")
_mcp_types = optional_import("mcp.types")

Server = getattr(_mcp_server, "Server", None)
stdio_server = getattr(_mcp_stdio, "stdio_server", None)
TextContent = getattr(_mcp_types, "TextContent", None)
Tool = getattr(_mcp_types, "Tool", None)

if Server is None or stdio_server is None or TextContent is None or Tool is None:  # pragma: no cover - lightweight fallback
    @dataclass(slots=True)
    class TextContent:
        type: str
        text: str

    @dataclass(slots=True)
    class Tool:
        name: str
        description: str
        inputSchema: dict[str, Any]

    class Server:
        def __init__(self, _name: str) -> None:
            self._list_tools = None
            self._call_tool = None

        def list_tools(self):
            def decorator(func):
                self._list_tools = func
                return func

            return decorator

        def call_tool(self):
            def decorator(func):
                self._call_tool = func
                return func

            return decorator

        def create_initialization_options(self) -> dict[str, Any]:
            return {}

        async def run(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("mcp package is not installed")

    @asynccontextmanager
    async def stdio_server():
        raise RuntimeError("mcp package is not installed")
        yield None, None


load_dotenv(ROOT / ".env")

SETTINGS = NetworkSettings()
APP = Server("multi-agent-fraud-network")
_NETWORK: FraudDetectionNetwork | None = None


def _network() -> FraudDetectionNetwork:
    global _NETWORK
    if _NETWORK is None:
        _NETWORK = FraudDetectionNetwork(SETTINGS)
    return _NETWORK


def _as_text(payload: dict[str, Any]) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, indent=2))]


async def describe_architecture() -> dict[str, Any]:
    return _network().architecture()


async def process_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    event = TransactionEvent.from_dict(transaction)
    result = await _network().process_event(event)
    return result.to_dict()


async def run_proof_of_concept() -> dict[str, Any]:
    fresh_network = FraudDetectionNetwork(NetworkSettings())
    return await fresh_network.run_proof_of_concept()


async def replay_paysim_stream(limit: int = 25) -> dict[str, Any]:
    return await _network().replay_paysim_stream(limit=limit)


async def seed_graph_from_csv(csv_path: str, clear_existing: bool = False) -> dict[str, Any]:
    csv_file = Path(csv_path)
    if not csv_file.exists():
        return {"status": "error", "message": f"CSV not found: {csv_path}"}
    frame = pd.read_csv(csv_file) if pd is not None else read_csv_records(csv_file)
    graph_backend = _network().graph_backend
    if clear_existing and hasattr(graph_backend, "clear"):
        graph_backend.clear()
    graph_backend.load(frame)
    return {
        "status": "seeded",
        "rows_loaded": len(frame),
        "rings": graph_backend.query_rings()[:5],
        "chains": graph_backend.query_chains()[:5],
        "hubs": graph_backend.query_hubs()[:5],
    }


@APP.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="describe_architecture",
            description="Return the six-agent architecture, Kafka topics, technology stack, and data strategy.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="process_realtime_transaction",
            description="Run a single transaction through the full multi-agent fraud network and return agent signals, risk, decision, and compliance artefacts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "transaction": {"type": "object"},
                },
                "required": ["transaction"],
            },
        ),
        Tool(
            name="run_proof_of_concept",
            description="Execute the real-world suspicious-login plus mule-chain proof-of-concept scenario.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="replay_paysim_stream",
            description="Replay PaySim events through the Kafka-style pipeline to validate throughput and outcomes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 25},
                },
            },
        ),
        Tool(
            name="seed_graph_from_csv",
            description="Seed the graph backend from a CSV file for Neo4j-style traversal and fraud-ring detection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "csv_path": {"type": "string"},
                    "clear_existing": {"type": "boolean", "default": False},
                },
                "required": ["csv_path"],
            },
        ),
    ]


@APP.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "describe_architecture":
            return _as_text(await describe_architecture())
        if name == "process_realtime_transaction":
            return _as_text(await process_transaction(arguments["transaction"]))
        if name == "run_proof_of_concept":
            return _as_text(await run_proof_of_concept())
        if name == "replay_paysim_stream":
            return _as_text(await replay_paysim_stream(limit=int(arguments.get("limit", 25))))
        if name == "seed_graph_from_csv":
            return _as_text(
                await seed_graph_from_csv(
                    csv_path=arguments["csv_path"],
                    clear_existing=bool(arguments.get("clear_existing", False)),
                )
            )
        return _as_text({"status": "error", "message": f"unknown tool: {name}"})
    except Exception as exc:  # pragma: no cover - surfaced to clients
        return _as_text({"status": "error", "message": str(exc), "tool": name})


async def main() -> None:
    async with stdio_server() as (reader, writer):
        await APP.run(reader, writer, APP.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
