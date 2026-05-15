from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def generate(rows: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Generate realistic names
    first_names = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Ayaan", "Krishna", "Ishaan", "Shaurya", "Diya", "Sanya", "Kavya", "Isha", "Neha", "Riya", "Aanya", "Ananya", "Sara", "Priya"]
    last_names = ["Sharma", "Patel", "Singh", "Kumar", "Das", "Bose", "Gupta", "Nair", "Iyer", "Rao", "Joshi", "Mehta", "Reddy", "Verma", "Yadav", "Chauhan", "Malhotra", "Kapoor", "Khan", "Zaidi"]
    
    num_accounts = max(400, rows // 8)
    accounts = [f"ACC-{idx:05d}" for idx in range(num_accounts)]
    account_names = {acc: f"{rng.choice(first_names)} {rng.choice(last_names)}" for acc in accounts}
    
    devices = [f"device-{idx:04d}" for idx in range(max(60, rows // 40))]
    ips = [f"103.{idx % 200}.{(idx * 3) % 200}.{(idx * 7) % 200}" for idx in range(max(90, rows // 35))]
    start = datetime(2026, 3, 1, 9, 0, 0)

    fraud_ring = ["ACC-RING-01", "ACC-RING-02", "ACC-RING-03", "ACC-RING-04"]
    for acc in fraud_ring:
        account_names[acc] = f"{rng.choice(first_names)} {rng.choice(last_names)}"
        
    mule_chain = ["ACC-MULE-01", "ACC-MULE-02", "ACC-MULE-03", "ACC-MULE-HUB"]
    for acc in mule_chain:
        account_names[acc] = f"{rng.choice(first_names)} {rng.choice(last_names)}"
        
    hub_senders = [f"ACC-HUB-SRC-{idx:02d}" for idx in range(1, 6)]
    for acc in hub_senders:
        account_names[acc] = f"{rng.choice(first_names)} {rng.choice(last_names)}"
        
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
                "sender_name": account_names[sender],
                "receiver_account": receiver,
                "receiver_name": account_names[receiver],
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
                "sender_name": account_names[sender],
                "receiver_account": receiver,
                "receiver_name": account_names[receiver],
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


import sys
import asyncio
from core.geo_utils import COUNTRY_COORDS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

async def seed_mongo_history():
    """Seed MongoDB with account login history and display names for Impossible Travel demos."""
    from core.config import NetworkSettings
    from core.db_service import MongoDBService
    
    settings = NetworkSettings()
    db = MongoDBService(settings.mongodb_uri, settings.mongodb_db)
    
    # Named synthetic accounts with realistic display names and login history
    named_accounts = [
        # account_id,   name,               country, lat,     lng,     hours_ago, login_count
        ("ACC-PRIMARY",    "Arjun Mehta",       "IN",  20.59,   78.96,   0.17,  12),
        ("ACC-MULE-01",    "Priya Sharma",      "US",  37.09,  -95.71,   2.0,    5),
        ("ACC-MULE-02",    "Ravi Kumar",        "AE",  23.42,   53.85,   3.5,    8),
        ("ACC-MULE-03",    "Sonal Patel",       "GB",  55.38,   -3.44,   5.0,    3),
        ("ACC-MULE-HUB",   "Vikram Nair",       "NG",   9.08,    8.68,   6.0,    2),
        ("ACC-RING-01",    "Aisha Khan",        "IN",  20.59,   78.96,   1.0,   15),
        ("ACC-RING-02",    "Dev Bose",          "IN",  20.59,   78.96,   1.5,    9),
        ("ACC-RING-03",    "Neha Gupta",        "IN",  20.59,   78.96,   2.0,    7),
        ("ACC-RING-04",    "Sameer Joshi",      "IN",  20.59,   78.96,   2.5,    6),
        ("ACC-HUB-SRC-01", "Tanvir Ahmed",      "IN",  20.59,   78.96,   0.5,   11),
        ("ACC-HUB-SRC-02", "Meera Iyer",        "IN",  20.59,   78.96,   0.7,    4),
        ("ACC-HUB-SRC-03", "Karan Malhotra",    "AE",  23.42,   53.85,   1.2,    3),
        ("ACC-HUB-SRC-04", "Fatima Zaidi",      "IN",  20.59,   78.96,   1.8,    2),
        ("ACC-HUB-SRC-05", "Rohit Verma",       "US",  37.09,  -95.71,   3.0,    6),
    ]

    for account_id, name, country, lat, lng, hours_ago, login_count in named_accounts:
        ts = datetime.utcnow() - timedelta(hours=hours_ago)
        # Upsert login record with name and set login_count directly (seeding)
        await db.logins.update_one(
            {"account_id": account_id},
            {"$set": {
                "country": country, "lat": lat, "lng": lng,
                "timestamp": ts, "name": name, "login_count": login_count,
                "account_id": account_id,
            }},
            upsert=True,
        )

    print(f"Seeded MongoDB history for {len(named_accounts)} named demo accounts at {settings.mongodb_uri}")
    await db.close()

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate graph-seeding fraud data with rings, mule chains, and hubs.")
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--seed-mongo", action="store_true", help="Seed MongoDB history for demo.")
    args = parser.parse_args()

    if args.seed_mongo:
        asyncio.run(seed_mongo_history())
    else:
        frame = generate(rows=args.rows, seed=args.seed)
        print(f"generated {len(frame):,} rows with {int(frame['is_fraud'].sum()):,} fraud labels -> {ROOT / 'data' / 'synthetic_fraud_graph_dataset.csv'}")


if __name__ == "__main__":
    main()
