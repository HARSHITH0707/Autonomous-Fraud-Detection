import json
import logging
import math
from datetime import datetime
from collections import defaultdict
from typing import Optional

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Agent02-BehaviourAnalyser")

ANOMALY_WEIGHTS = {
    "AMOUNT_SPIKE":        0.40,
    "NEW_DEVICE":          0.35,
    "NEW_IP_SUBNET":       0.25,
    "UNUSUAL_HOUR":        0.20,
    "NEW_TXN_TYPE":        0.15,
    "RECEIVER_ANOMALY":    0.20,
    "FREQUENCY_SPIKE":     0.30,
}

MIN_PROFILE_TXNS = 3


class UserProfile:
    def __init__(self, account_id: str):
        self.account_id       = account_id
        self.txn_count        = 0
        self.amounts          = []
        self.avg_amount       = 0.0
        self.std_amount       = 0.0
        self.hour_counts      = defaultdict(int)
        self.usual_hours      = set()
        self.known_devices    = set()
        self.known_ip_subnets = set()
        self.txn_type_counts  = defaultdict(int)
        self.usual_txn_types  = set()
        self.known_receivers  = set()
        self.receiver_counts  = defaultdict(int)
        self.daily_counts     = defaultdict(int)
        self.avg_daily_count  = 0.0

    def update(self, transaction: dict):
        self.txn_count += 1
        amount   = float(transaction.get("amount", 0))
        device   = transaction.get("device_id", "")
        ip       = transaction.get("ip_address", "")
        txn_type = transaction.get("transaction_type", "")
        receiver = transaction.get("receiver_account", "")
        ts_raw   = transaction.get("timestamp", datetime.now().isoformat())

        try:
            if isinstance(ts_raw, str):
                ts = datetime.fromisoformat(ts_raw.replace("T", " ").split(".")[0])
            else:
                ts = ts_raw
        except Exception:
            ts = datetime.now()

        self.amounts.append(amount)
        self.avg_amount = sum(self.amounts) / len(self.amounts)
        if len(self.amounts) > 1:
            mean = self.avg_amount
            variance = sum((x - mean) ** 2 for x in self.amounts) / len(self.amounts)
            self.std_amount = math.sqrt(variance)

        hour = ts.hour
        self.hour_counts[hour] += 1
        if self.hour_counts[hour] >= 2:
            self.usual_hours.add(hour)

        if device:
            self.known_devices.add(device)

        if ip:
            subnet = ".".join(ip.split(".")[:2])
            self.known_ip_subnets.add(subnet)

        self.txn_type_counts[txn_type] += 1
        if self.txn_type_counts[txn_type] >= 2:
            self.usual_txn_types.add(txn_type)

        if receiver:
            self.known_receivers.add(receiver)
            self.receiver_counts[receiver] += 1

        date_key = ts.strftime("%Y-%m-%d")
        self.daily_counts[date_key] += 1
        if self.daily_counts:
            self.avg_daily_count = sum(self.daily_counts.values()) / len(self.daily_counts)

    def is_mature(self) -> bool:
        return self.txn_count >= MIN_PROFILE_TXNS

    def to_dict(self) -> dict:
        return {
            "account_id":       self.account_id,
            "txn_count":        self.txn_count,
            "avg_amount":       round(self.avg_amount, 2),
            "std_amount":       round(self.std_amount, 2),
            "usual_hours":      sorted(self.usual_hours),
            "known_devices":    len(self.known_devices),
            "known_ip_subnets": len(self.known_ip_subnets),
            "usual_txn_types":  list(self.usual_txn_types),
            "known_receivers":  len(self.known_receivers),
            "avg_daily_txns":   round(self.avg_daily_count, 2),
            "profile_mature":   self.is_mature(),
        }


class BehaviourAnalyserAgent:

    def __init__(self):
        self.profiles: dict = {}
        self.total_trained = 0
        log.info("BehaviourAnalyserAgent initialized")

    def train_on_history(self, transactions: list):
        log.info(f"Training on {len(transactions):,} historical transactions...")
        for txn in transactions:
            sender = txn.get("sender_account", "")
            if not sender:
                continue
            if sender not in self.profiles:
                self.profiles[sender] = UserProfile(sender)
            self.profiles[sender].update(txn)
        self.total_trained = len(transactions)
        mature_count = sum(1 for p in self.profiles.values() if p.is_mature())
        log.info(f"Profiles built: {len(self.profiles):,} accounts ({mature_count:,} mature)")

    def analyze(self, transaction: dict) -> dict:
        sender   = transaction.get("sender_account", "")
        txn_id   = transaction.get("transaction_id", "UNKNOWN")
        amount   = float(transaction.get("amount", 0))
        device   = transaction.get("device_id", "")
        ip       = transaction.get("ip_address", "")
        txn_type = transaction.get("transaction_type", "")
        receiver = transaction.get("receiver_account", "")
        ts_raw   = transaction.get("timestamp", datetime.now().isoformat())

        try:
            if isinstance(ts_raw, str):
                ts = datetime.fromisoformat(ts_raw.replace("T", " ").split(".")[0])
            else:
                ts = ts_raw
        except Exception:
            ts = datetime.now()

        anomalies = []
        details   = []

        if sender not in self.profiles:
            self.profiles[sender] = UserProfile(sender)
            return self._new_account_result(txn_id, sender)

        profile = self.profiles[sender]

        if not profile.is_mature():
            return self._immature_profile_result(txn_id, sender, profile.txn_count)

        if profile.std_amount > 0:
            z_score = (amount - profile.avg_amount) / profile.std_amount
            if z_score > 3.0:
                anomalies.append("AMOUNT_SPIKE")
                details.append(f"Amount {amount:,.0f} is {z_score:.1f} sigma above normal")
        elif amount > profile.avg_amount * 5:
            anomalies.append("AMOUNT_SPIKE")
            details.append(f"Amount {amount:,.0f} is 5x above usual {profile.avg_amount:,.0f}")

        if device and device not in profile.known_devices:
            anomalies.append("NEW_DEVICE")
            details.append(f"Device '{device}' never seen before")

        if ip:
            subnet = ".".join(ip.split(".")[:2])
            if subnet not in profile.known_ip_subnets:
                anomalies.append("NEW_IP_SUBNET")
                details.append(f"IP subnet {subnet}.x.x is new — possible location change")

        hour = ts.hour
        if profile.usual_hours and hour not in profile.usual_hours:
            anomalies.append("UNUSUAL_HOUR")
            details.append(f"Transacting at hour {hour:02d} — unusual for this account")

        if txn_type and profile.usual_txn_types and txn_type not in profile.usual_txn_types:
            anomalies.append("NEW_TXN_TYPE")
            details.append(f"Transaction type '{txn_type}' unusual for this account")

        if receiver:
            recv_count = profile.receiver_counts.get(receiver, 0)
            if recv_count == 0 and len(profile.known_receivers) > 5:
                anomalies.append("RECEIVER_ANOMALY")
                details.append(f"Receiver {receiver} never seen before")

        date_key = ts.strftime("%Y-%m-%d")
        today_count = profile.daily_counts.get(date_key, 0)
        if profile.avg_daily_count > 0 and today_count > profile.avg_daily_count * 4:
            anomalies.append("FREQUENCY_SPIKE")
            details.append(f"Made {today_count} txns today — avg is {profile.avg_daily_count:.1f}/day")

        behaviour_score = min(
            sum(ANOMALY_WEIGHTS.get(a, 0.1) for a in anomalies),
            1.0
        )

        profile.update(transaction)

        result = {
            "agent":           "BehaviourAnalyser",
            "transaction_id":  txn_id,
            "sender":          sender,
            "anomalies":       anomalies,
            "anomaly_count":   len(anomalies),
            "behaviour_score": round(behaviour_score, 4),
            "details":         details,
            "profile_snapshot": {
                "txn_count":  profile.txn_count,
                "avg_amount": round(profile.avg_amount, 2),
                "std_amount": round(profile.std_amount, 2),
            },
            "flagged": behaviour_score >= 0.35,
        }

        if anomalies:
            log.warning(f"[{txn_id}] Behaviour anomaly | score={behaviour_score:.2f}")
        else:
            log.info(f"[{txn_id}] Normal behaviour")

        return result

    def analyze_batch(self, transactions: list) -> list:
        return [self.analyze(txn) for txn in transactions]

    def get_profile(self, account_id: str):
        if account_id in self.profiles:
            return self.profiles[account_id].to_dict()
        return None

    def get_all_profiles_summary(self) -> dict:
        return {
            "total_accounts":     len(self.profiles),
            "mature_profiles":    sum(1 for p in self.profiles.values() if p.is_mature()),
            "total_trained_txns": self.total_trained,
        }

    def _new_account_result(self, txn_id: str, sender: str) -> dict:
        return {
            "agent":           "BehaviourAnalyser",
            "transaction_id":  txn_id,
            "sender":          sender,
            "anomalies":       ["NEW_ACCOUNT"],
            "anomaly_count":   1,
            "behaviour_score": 0.3,
            "details":         ["Account has no transaction history"],
            "flagged":         False,
        }

    def _immature_profile_result(self, txn_id: str, sender: str, txn_count: int) -> dict:
        return {
            "agent":           "BehaviourAnalyser",
            "transaction_id":  txn_id,
            "sender":          sender,
            "anomalies":       [],
            "anomaly_count":   0,
            "behaviour_score": 0.1,
            "details":         [f"Profile immature ({txn_count}/{MIN_PROFILE_TXNS} txns seen)"],
            "flagged":         False,
        }


if __name__ == "__main__":
    agent = BehaviourAnalyserAgent()
    history = [
        {
            "transaction_id":   f"HIST_{i:03d}",
            "timestamp":        f"2024-01-{10+i:02d}T10:00:00",
            "sender_account":   "ACC000123",
            "receiver_account": "ACC000001",
            "amount":           500.0,
            "transaction_type": "TRANSFER",
            "device_id":        "device-abc",
            "ip_address":       "192.168.1.5",
        }
        for i in range(5)
    ]
    agent.train_on_history(history)
    print("\n" + "="*60)
    print("  AGENT 02 - Behaviour Analyser Test")
    print("="*60)
    test = {
        "transaction_id":   "TXN_FRAUD",
        "timestamp":        "2024-02-01T03:15:00",
        "sender_account":   "ACC000123",
        "receiver_account": "ACC000999",
        "amount":           75000.0,
        "transaction_type": "CASH_OUT",
        "device_id":        "device-STOLEN",
        "ip_address":       "10.99.1.1",
    }
    result = agent.analyze(test)
    print(f"Score:     {result['behaviour_score']}")
    print(f"Flagged:   {result['flagged']}")
    print(f"Anomalies: {result['anomalies']}")

