import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Optional

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Agent06-ComplianceLogger")

DEFAULT_OUTPUT_DIR = Path("outputs")

REGULATORY_REFS = {
    "BLOCK":         "RBI/DPSS/CO/PD/No.1810/02.14.003/2020-21",
    "OTP_CHALLENGE": "RBI/2019-20/142 — Customer Protection",
    "ALLOW":         None,
}

REPORTABLE_ACTIONS     = ["BLOCK"]
REPORTABLE_MIN_AMOUNT  = 10_000


class ComplianceLogger:

    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
        self.output_dir.mkdir(exist_ok=True)

        self.log_file   = self.output_dir / "compliance_log.jsonl"
        self.csv_file   = self.output_dir / "fraud_report.csv"
        self.stats_file = self.output_dir / "agent_stats.json"

        self.stats = {
            "total_logged":           0,
            "total_blocked":          0,
            "total_otp":              0,
            "total_allowed":          0,
            "total_amount_protected": 0.0,
            "by_date":                defaultdict(int),
            "by_action":              defaultdict(int),
        }

        self._init_csv()
        log.info(f"ComplianceLogger initialized | output: {self.output_dir}")

    def log_decision(self,
                     transaction: dict,
                     decision: dict,
                     monitor_result:    Optional[dict] = None,
                     behaviour_result:  Optional[dict] = None,
                     ml_result:         Optional[dict] = None,
                     graph_result:      Optional[dict] = None) -> dict:

        txn_id = transaction.get("transaction_id", "UNKNOWN")
        amount = float(transaction.get("amount", 0))
        action = decision.get("action", "UNKNOWN")
        score  = decision.get("final_score", 0)
        ts_now = datetime.now().isoformat()

        log_entry = {
            "log_id":         f"LOG_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "logged_at":      ts_now,
            "transaction_id": txn_id,
            "transaction": {
                "id":        txn_id,
                "timestamp": transaction.get("timestamp"),
                "sender":    transaction.get("sender_account"),
                "receiver":  transaction.get("receiver_account"),
                "amount":    amount,
                "type":      transaction.get("transaction_type"),
                "device_id": transaction.get("device_id"),
                "ip_address":transaction.get("ip_address"),
            },
            "decision": {
                "action":           action,
                "final_score":      score,
                "risk_level":       decision.get("risk_level"),
                "component_scores": decision.get("component_scores", {}),
                "reasoning":        decision.get("reasoning", []),
                "decision_time_ms": decision.get("decision_time_ms", 0),
            },
            "evidence": {
                "transaction_monitor": {
                    "alerts":      monitor_result.get("alerts", [])        if monitor_result   else [],
                    "alert_score": monitor_result.get("alert_score", 0)    if monitor_result   else 0,
                },
                "behaviour_analyser": {
                    "anomalies":       behaviour_result.get("anomalies", [])      if behaviour_result else [],
                    "behaviour_score": behaviour_result.get("behaviour_score", 0) if behaviour_result else 0,
                },
                "ml_models": {
                    "general_ml_prob": ml_result.get("general_ml_prob")      if ml_result else None,
                    "paysim_ml_prob":  ml_result.get("paysim_ml_prob")       if ml_result else None,
                    "ensemble_score":  ml_result.get("ensemble_fraud_score") if ml_result else None,
                },
                "graph_detector": {
                    "risk_score": graph_result.get("risk_score", 0)  if graph_result else 0,
                    "fraud_sent": graph_result.get("fraud_sent", 0)  if graph_result else 0,
                    "fraud_recv": graph_result.get("fraud_recv", 0)  if graph_result else 0,
                    "shared_dev": graph_result.get("shared_dev", 0)  if graph_result else 0,
                },
            },
            "regulatory": {
                "reportable":     action in REPORTABLE_ACTIONS and amount >= REPORTABLE_MIN_AMOUNT,
                "regulatory_ref": REGULATORY_REFS.get(action),
                "report_to":      ["RBI", "FIU-IND"] if action == "BLOCK" and amount >= 100_000 else [],
                "case_reference": f"CASE-{txn_id}-{datetime.now().strftime('%Y%m%d')}",
            },
        }

        with open(self.log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        if action in REPORTABLE_ACTIONS:
            self._append_to_csv(log_entry)

        self.stats["total_logged"] += 1
        self.stats["by_action"][action] += 1
        self.stats["by_date"][ts_now[:10]] += 1

        if action == "BLOCK":
            self.stats["total_blocked"]          += 1
            self.stats["total_amount_protected"] += amount
        elif action == "OTP_CHALLENGE":
            self.stats["total_otp"]     += 1
        else:
            self.stats["total_allowed"] += 1

        self._save_stats()

        log.info(f"[{txn_id}] Logged | action={action} | "
                 f"reportable={log_entry['regulatory']['reportable']}")

        return log_entry

    def generate_rbi_report(self, date: str = None) -> str:
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        report_file = self.output_dir / f"rbi_report_{date.replace('-', '')}.txt"

        day_entries = []
        if self.log_file.exists():
            with open(self.log_file) as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("logged_at", "")[:10] == date:
                            day_entries.append(entry)
                    except Exception:
                        continue

        reportable   = [e for e in day_entries if e.get("regulatory", {}).get("reportable")]
        total_blocked = sum(1 for e in day_entries if e["decision"]["action"] == "BLOCK")
        total_amount  = sum(
            e["transaction"]["amount"]
            for e in day_entries
            if e["decision"]["action"] == "BLOCK"
        )

        lines = [
            "=" * 70,
            "FRAUD INCIDENT REPORT",
            "Submitted to: Reserve Bank of India (RBI)",
            f"Report Date: {date}",
            f"Report Reference: RBI-FRAUD-{date.replace('-', '')}-001",
            "=" * 70,
            "",
            "SECTION 1: SUMMARY",
            "-" * 40,
            f"Total Transactions Analyzed : {len(day_entries)}",
            f"Transactions Blocked        : {total_blocked}",
            f"Total Amount Protected      : {total_amount:,.2f}",
            f"Reportable Fraud Cases      : {len(reportable)}",
            "",
            "SECTION 2: FRAUD CASES",
            "-" * 40,
        ]

        if reportable:
            for i, entry in enumerate(reportable, 1):
                txn = entry["transaction"]
                dec = entry["decision"]
                reg = entry["regulatory"]
                lines += [
                    f"",
                    f"CASE {i}: {reg['case_reference']}",
                    f"  Transaction ID : {txn['id']}",
                    f"  Sender Account : {txn['sender']}",
                    f"  Amount         : {txn['amount']:,.2f}",
                    f"  Action Taken   : {dec['action']}",
                    f"  Fraud Score    : {dec['final_score']}",
                    f"  Risk Level     : {dec['risk_level']}",
                    f"  Regulatory Ref : {reg['regulatory_ref']}",
                ]
        else:
            lines.append("  No reportable fraud cases for this date.")

        lines += [
            "",
            "=" * 70,
            "SECTION 3: COMPLIANCE",
            "-" * 40,
            "Auto-generated by Autonomous Fraud Detection & Response Network",
            "Compliant with RBI Master Direction on Fraud Classification",
            f"Generated at: {datetime.now().isoformat()}",
            "=" * 70,
        ]

        with open(report_file, "w") as f:
            f.write("\n".join(lines))

        log.info(f"RBI Report generated: {report_file}")
        return str(report_file)

    def get_stats(self) -> dict:
        return {
            "total_logged":           self.stats["total_logged"],
            "total_blocked":          self.stats["total_blocked"],
            "total_otp_challenged":   self.stats["total_otp"],
            "total_allowed":          self.stats["total_allowed"],
            "total_amount_protected": round(self.stats["total_amount_protected"], 2),
            "log_file":               str(self.log_file),
            "csv_file":               str(self.csv_file),
        }

    def _init_csv(self):
        if not self.csv_file.exists():
            with open(self.csv_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "log_id", "logged_at", "transaction_id",
                    "sender", "receiver", "amount", "txn_type",
                    "action", "final_score", "risk_level",
                    "ml_score", "graph_score", "behaviour_score",
                    "graph_risk_raw", "alerts", "anomalies",
                    "regulatory_ref", "case_reference"
                ])

    def _append_to_csv(self, log_entry: dict):
        txn = log_entry["transaction"]
        dec = log_entry["decision"]
        ev  = log_entry["evidence"]
        reg = log_entry["regulatory"]
        cs  = dec.get("component_scores", {})

        with open(self.csv_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                log_entry["log_id"],
                log_entry["logged_at"],
                txn["id"],
                txn["sender"],
                txn["receiver"],
                txn["amount"],
                txn["type"],
                dec["action"],
                dec["final_score"],
                dec["risk_level"],
                cs.get("ml_score", ""),
                cs.get("graph_score", ""),
                cs.get("behaviour_score", ""),
                ev["graph_detector"]["risk_score"],
                "|".join(ev["transaction_monitor"]["alerts"]),
                "|".join(ev["behaviour_analyser"]["anomalies"]),
                reg.get("regulatory_ref", ""),
                reg.get("case_reference", ""),
            ])

    def _save_stats(self):
        save_stats = dict(self.stats)
        save_stats["by_date"]   = dict(self.stats["by_date"])
        save_stats["by_action"] = dict(self.stats["by_action"])
        with open(self.stats_file, "w") as f:
            json.dump(save_stats, f, indent=2)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        logger = ComplianceLogger(output_dir=tmp)
        print("\n" + "="*60)
        print("  AGENT 06 - Compliance Logger Test")
        print("="*60)
        test_txn = {
            "transaction_id":   "TXN_FRAUD_001",
            "timestamp":        "2024-03-15T03:30:00",
            "sender_account":   "ACC000123",
            "receiver_account": "ACC000999",
            "amount":           250000,
            "transaction_type": "CASH_OUT",
            "device_id":        "device-stolen",
            "ip_address":       "10.99.1.1",
        }
        test_decision = {
            "action":            "BLOCK",
            "final_score":       0.87,
            "risk_level":        "CRITICAL",
            "component_scores":  {"ml_score": 0.87, "graph_score": 0.9},
            "reasoning":         ["ML flagged 0.87", "New device"],
            "decision_time_ms":  38,
        }
        entry = logger.log_decision(
            transaction = test_txn,
            decision    = test_decision,
        )
        print(f"Logged:     {entry['log_id']}")
        print(f"Reportable: {entry['regulatory']['reportable']}")
        report = logger.generate_rbi_report()
        print(f"RBI Report: {report}")
        print(json.dumps(logger.get_stats(), indent=2))

