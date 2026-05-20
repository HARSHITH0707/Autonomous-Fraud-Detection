import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator

# Local SQLite fallback for audit logs
SQLITE_PATH = os.environ.get("SQLITE_URL", "local_audit.db")

db_firestore = None
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    
    if not firebase_admin._apps:
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            firebase_admin.initialize_app()
            
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        db_firestore = firestore.client()
except Exception as e:
    print(f"Firestore init error: {e}")

@contextmanager
def _connection() -> Iterator[Any]:
    conn = sqlite3.connect(SQLITE_PATH)
    try:
        yield conn
    finally:
        conn.close()

def init_db() -> None:
    ddl = """
        CREATE TABLE IF NOT EXISTS users (
            uid TEXT PRIMARY KEY,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            sender_account TEXT,
            receiver_account TEXT,
            amount REAL,
            decision TEXT,
            composite_risk REAL,
            full_payload TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """

    with _connection() as conn:
        cursor = conn.cursor()
        for statement in ddl.split(";"):
            stmt = statement.strip()
            if stmt:
                cursor.execute(stmt)
        conn.commit()

def save_transaction(result: Dict[str, Any]) -> None:
    txn = result["transaction"]
    
    # 1. Write to Firestore if available
    if db_firestore is not None:
        try:
            from firebase_admin import firestore
            doc_ref = db_firestore.collection("fraud_transactions").document(txn["transaction_id"])
            doc_ref.set({
                "transaction_id": txn["transaction_id"],
                "sender_account": txn["sender_account"],
                "receiver_account": txn["receiver_account"],
                "amount": txn["amount"],
                "decision": result["decision"]["decision"],
                "composite_risk": result["risk"]["composite_risk"],
                "full_payload": json.dumps(result),
                "processed_at": firestore.SERVER_TIMESTAMP
            }, merge=True)
        except Exception as e:
            print(f"Firestore Error: {e}")

    # 2. Write to local SQLite (Audit log)
    try:
        sql = """
            INSERT OR REPLACE INTO transactions (
                transaction_id, sender_account, receiver_account,
                amount, decision, composite_risk, full_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            txn["transaction_id"],
            txn["sender_account"],
            txn["receiver_account"],
            txn["amount"],
            result["decision"]["decision"],
            result["risk"]["composite_risk"],
            json.dumps(result),
        )

        with _connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
    except Exception as e:
        print(f"SQL Database Error: {e}")

init_db()
