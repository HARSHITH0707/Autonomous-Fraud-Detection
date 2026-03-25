from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import NetworkSettings
from core.models import TransactionEvent
from orchestration import FraudDetectionNetwork


async def run_cli(mode: str, output_path: str | None, limit: int) -> dict:
    network = FraudDetectionNetwork(NetworkSettings())
    if mode == "architecture":
        result = network.architecture()
    elif mode == "poc":
        result = await network.run_proof_of_concept()
    elif mode == "stream":
        result = await network.replay_paysim_stream(limit=limit)
    else:
        event = network.data_strategy.proof_of_concept_event()
        result = (await network.process_event(event)).to_dict()

    if output_path:
        Path(output_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the multi-agent fraud detection network.")
    parser.add_argument(
        "--mode",
        choices=["architecture", "poc", "stream", "single"],
        default="poc",
        help="Which pipeline mode to execute.",
    )
    parser.add_argument("--limit", type=int, default=25, help="Number of PaySim events to replay in stream mode.")
    parser.add_argument("--output", default=None, help="Optional JSON file to save the result.")
    args = parser.parse_args()

    result = asyncio.run(run_cli(args.mode, args.output, args.limit))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
