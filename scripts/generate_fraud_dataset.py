"""
Synthetic Fraud Dataset Generator
===================================
Generates synthetic_fraud_graph_dataset.csv for use with the MCP server.

Usage:
    python scripts/generate_fraud_dataset.py --rows 10000 --fraud-rate 0.05
"""

import argparse
import random
import uuid
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def generate(n_rows: int = 10000, fraud_rate: float = 0.05, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    random.seed(seed)

    # Pools
    n_accounts = max(200, n_rows // 10)
    n_devices  = max(50,  n_rows // 50)
    n_ips      = max(80,  n_rows // 40)

    accounts = [f"ACC{i:06d}" for i in range(n_accounts)]
    devices  = [str(uuid.uuid4())[:13] for _ in range(n_devices)]
    ips      = [f"192.168.{rng.integers(0,255)}.{rng.integers(1,254)}" for _ in range(n_ips)]

    # Fraud rings — small groups that transact among themselves
    fraud_accounts = random.sample(accounts, k=int(n_accounts * 0.05))

    rows = []
    start_time = datetime(2024, 1, 1)

    for i in range(n_rows):
        is_fraud = rng.random() < fraud_rate

        if is_fraud and fraud_accounts:
            sender   = random.choice(fraud_accounts)
            receiver = random.choice(fraud_accounts)
            while receiver == sender:
                receiver = random.choice(fraud_accounts)
            amount = round(float(rng.uniform(5000, 50000)), 2)
            device = random.choice(devices[:n_devices // 5])   # shared devices
            ip     = random.choice(ips[:n_ips // 5])           # shared IPs
        else:
            sender   = random.choice(accounts)
            receiver = random.choice(accounts)
            while receiver == sender:
                receiver = random.choice(accounts)
            amount = round(float(rng.exponential(500)), 2)
            device = random.choice(devices)
            ip     = random.choice(ips)

        txn_type  = random.choice(["TRANSFER", "PAYMENT", "CASH_OUT", "DEBIT"])
        timestamp = start_time + timedelta(
            seconds=int(rng.integers(0, 365 * 24 * 3600))
        )

        rows.append({
            "transaction_id":   f"TXN{i:08d}",
            "timestamp":        timestamp.isoformat(),
            "sender_account":   sender,
            "receiver_account": receiver,
            "amount":           amount,
            "transaction_type": txn_type,
            "device_id":        device,
            "ip_address":       ip,
            "is_fraud":         int(is_fraud),
        })

    df = pd.DataFrame(rows)
    out = ROOT / "data" / "synthetic_fraud_graph_dataset.csv"
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Generated {len(df):,} rows ({df['is_fraud'].sum()} fraud) -> {out}")
    return df


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--rows",       type=int,   default=10000)
    p.add_argument("--fraud-rate", type=float, default=0.05)
    p.add_argument("--seed",       type=int,   default=42)
    args = p.parse_args()
    generate(args.rows, args.fraud_rate, args.seed)
