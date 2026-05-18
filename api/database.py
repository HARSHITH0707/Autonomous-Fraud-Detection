import os
import sqlite3
import json
from typing import Any, Dict

# This acts as the SQL Connect integration layer.
# In a real Firebase Data Connect environment, this would use asyncpg/psycopg2 to connect 
# to the Cloud SQL PostgreSQL instance, or use the Firebase Admin SDK to execute Data Connect operations.
DB_PATH = os.environ.get("SQL_CONNECT_URL", "sql_connect_local.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create User Profiles Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            uid TEXT PRIMARY KEY,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create Transactions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            sender_account TEXT,
            receiver_account TEXT,
            amount REAL,
            decision TEXT,
            composite_risk REAL,
            full_payload TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def save_transaction(result: Dict[str, Any]):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO transactions (
                transaction_id, sender_account, receiver_account, 
                amount, decision, composite_risk, full_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            result["transaction"]["transaction_id"],
            result["transaction"]["sender_account"],
            result["transaction"]["receiver_account"],
            result["transaction"]["amount"],
            result["decision"]["decision"],
            result["risk"]["composite_risk"],
            json.dumps(result)
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"SQL Connect Error: {e}")

init_db()
