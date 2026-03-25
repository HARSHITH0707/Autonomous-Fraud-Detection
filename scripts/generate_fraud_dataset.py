from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def generate(rows: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    accounts = [f"ACC-{idx:05d}" for idx in range(max(400, rows // 8))]
    devices = [f"device-{idx:04d}" for idx in range(max(60, rows // 40))]
    ips = [f"103.{idx % 200}.{(idx * 3) % 200}.{(idx * 7) % 200}" for idx in range(max(90, rows // 35))]
    start = datetime(2026, 3, 1, 9, 0, 0)

    fraud_ring = ["ACC-RING-01", "ACC-RING-02", "ACC-RING-03", "ACC-RING-04"]
    mule_chain = ["ACC-MULE-01", "ACC-MULE-02", "ACC-MULE-03", "ACC-MULE-HUB"]
    hub_senders = [f"ACC-HUB-SRC-{idx:02d}" for idx in range(1, 6)]
    shared_device = "device-shared-fraud"

    rows_out: list[dict] = []

    for idx in range(rows):
        timestamp = start + timedelta(seconds=int(idx * 45))
        amount = round(float(rng.exponential(2500.0) + 200), 2)
        sender = str(rng.choice(accounts))
        receiver = str(rng.choice(accounts))
        while receiver == sender:
            receiver = str(rng.choice(accounts))

        rows_out.append(
            {
                "transaction_id": f"TXN-{idx:07d}",
                "timestamp": timestamp.isoformat(),
                "sender_account": sender,
                "receiver_account": receiver,
                "amount": amount,
                "transaction_type": str(rng.choice(["UPI", "CARD", "NET_BANKING", "CRYPTO"])),
                "device_id": str(rng.choice(devices)),
                "ip_address": str(rng.choice(ips)),
                "is_fraud": int(amount > 9000 and rng.random() > 0.93),
            }
        )

    base_index = len(rows_out)

    for offset in range(len(fraud_ring)):
        sender = fraud_ring[offset]
        receiver = fraud_ring[(offset + 1) % len(fraud_ring)]
        rows_out.append(
            {
                "transaction_id": f"TXN-RING-{offset:03d}",
                "timestamp": (start + timedelta(hours=12, minutes=offset)).isoformat(),
                "sender_account": sender,
                "receiver_account": receiver,
                "amount": 42000 + offset * 1500,
                "transaction_type": "UPI",
                "device_id": shared_device,
                "ip_address": f"196.12.55.{10 + offset}",
                "is_fraud": 1,
            }
        )

    for offset in range(len(mule_chain) - 1):
        rows_out.append(
            {
                "transaction_id": f"TXN-MULE-{offset:03d}",
                "timestamp": (start + timedelta(hours=13, minutes=offset * 2)).isoformat(),
                "sender_account": mule_chain[offset],
                "receiver_account": mule_chain[offset + 1],
                "amount": 85000 - offset * 2000,
                "transaction_type": "UPI",
                "device_id": shared_device if offset < 2 else "device-mule-last",
                "ip_address": f"196.12.60.{20 + offset}",
                "is_fraud": 1,
            }
        )

    for offset, sender in enumerate(hub_senders):
        rows_out.append(
            {
                "transaction_id": f"TXN-HUB-{offset:03d}",
                "timestamp": (start + timedelta(hours=14, minutes=offset)).isoformat(),
                "sender_account": sender,
                "receiver_account": "ACC-MULE-HUB",
                "amount": 51000 + offset * 1000,
                "transaction_type": "NET_BANKING",
                "device_id": shared_device,
                "ip_address": f"196.12.70.{30 + offset}",
                "is_fraud": 1,
            }
        )

    frame = pd.DataFrame(rows_out)
    output = ROOT / "data" / "synthetic_fraud_graph_dataset.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate graph-seeding fraud data with rings, mule chains, and hubs.")
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    frame = generate(rows=args.rows, seed=args.seed)
    print(f"generated {len(frame):,} rows with {int(frame['is_fraud'].sum()):,} fraud labels -> {ROOT / 'data' / 'synthetic_fraud_graph_dataset.csv'}")


if __name__ == "__main__":
    main()
