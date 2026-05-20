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
            uid TEXT,
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
        try:
            cursor.execute("ALTER TABLE transactions ADD COLUMN uid TEXT;")
        except sqlite3.OperationalError:
            pass
        conn.commit()

def save_transaction(result: Dict[str, Any], uid: str | None = None) -> None:
    txn = result["transaction"]
    
    # 1. Write to Firestore if available
    if db_firestore is not None:
        try:
            from firebase_admin import firestore
            doc_ref = db_firestore.collection("fraud_transactions").document(txn["transaction_id"])
            doc_data = {
                "transaction_id": txn["transaction_id"],
                "sender_account": txn["sender_account"],
                "receiver_account": txn["receiver_account"],
                "amount": txn["amount"],
                "decision": result["decision"]["decision"],
                "composite_risk": result["risk"]["composite_risk"],
                "full_payload": json.dumps(result),
                "processed_at": firestore.SERVER_TIMESTAMP
            }
            if uid:
                doc_data["uid"] = uid
            doc_ref.set(doc_data, merge=True)
        except Exception as e:
            print(f"Firestore Error: {e}")

    # 2. Write to local SQLite (Audit log)
    try:
        sql = """
            INSERT OR REPLACE INTO transactions (
                transaction_id, uid, sender_account, receiver_account,
                amount, decision, composite_risk, full_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            txn["transaction_id"],
            uid,
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

def get_user_transactions(uid: str, limit: int = 40) -> list[Dict[str, Any]]:
    # 1. Try fetching from Firestore if available
    if db_firestore is not None:
        try:
            runs_ref = db_firestore.collection("fraud_transactions")
            query = runs_ref.filter("uid", "==", uid).order_by("processed_at", direction="DESCENDING").limit(limit)
            docs = query.stream()
            results = []
            for doc in docs:
                data = doc.to_dict()
                results.append(json.loads(data["full_payload"]))
            return list(reversed(results))
        except Exception as e:
            print(f"Firestore query error, falling back to SQLite: {e}")

    # 2. Fall back to local SQLite
    try:
        sql = """
            SELECT full_payload FROM transactions
            WHERE uid = ?
            ORDER BY processed_at DESC
            LIMIT ?
        """
        with _connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (uid, limit))
            rows = cursor.fetchall()
            results = [json.loads(row[0]) for row in rows]
            return list(reversed(results))
    except Exception as e:
        print(f"SQL Database fetch error: {e}")
        return []

init_db()
