"""
Neo4j Fraud Graph — core graph database logic.
Extracted from app.py and importable by the MCP server.
"""

import os
import time
import pandas as pd
from neo4j import GraphDatabase

BATCH = 500


class Neo4jFraudGraph:
    """All Neo4j operations: connect, load, query, extract features."""

    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self.uri  = uri  or os.getenv("NEO4J_URI",      "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER",     "neo4j")
        self.pw   = password or os.getenv("NEO4J_PASSWORD", "frauddetection123")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.pw))
        print(f"  Neo4j connected  -->  {self.uri}")

    def close(self):
        self.driver.close()

    def __enter__(self):  return self
    def __exit__(self, *_): self.close()

    def run(self, cypher: str, params: dict = None):
        with self.driver.session() as s:
            return s.run(cypher, params or {}).data()

    def run_write(self, cypher: str, params: dict = None):
        with self.driver.session() as s:
            s.execute_write(lambda tx: tx.run(cypher, params or {}))

    # ── schema ──────────────────────────────────────────────────────────────

    def setup_schema(self):
        print("  Setting up schema ...")
        for c in [
            "CREATE CONSTRAINT account_id IF NOT EXISTS FOR (a:Account) REQUIRE a.account_id IS UNIQUE",
            "CREATE CONSTRAINT device_uid IF NOT EXISTS FOR (d:Device)  REQUIRE d.device_id  IS UNIQUE",
            "CREATE CONSTRAINT ip_addr    IF NOT EXISTS FOR (i:IP)      REQUIRE i.address     IS UNIQUE",
        ]:
            try:
                self.run_write(c)
            except Exception:
                pass

    def clear(self):
        print("  Clearing database ...")
        self.run_write("MATCH (n) DETACH DELETE n")

    # ── data loading ─────────────────────────────────────────────────────────

    def load(self, df: pd.DataFrame):
        t0 = time.time()
        print(f"\n  Loading {len(df):,} rows into Neo4j ...")

        # 1. Account nodes
        accts = list(set(df.sender_account) | set(df.receiver_account))
        for i in range(0, len(accts), BATCH):
            self.run_write(
                "UNWIND $b AS r MERGE (:Account {account_id: r.id})",
                {"b": [{"id": a} for a in accts[i:i+BATCH]]})

        # 2. Device nodes
        devs = df.device_id.dropna().unique().tolist()
        for i in range(0, len(devs), BATCH):
            self.run_write(
                "UNWIND $b AS r MERGE (:Device {device_id: r.id})",
                {"b": [{"id": d} for d in devs[i:i+BATCH]]})

        # 3. IP nodes
        ips = df.ip_address.dropna().unique().tolist()
        for i in range(0, len(ips), BATCH):
            self.run_write(
                "UNWIND $b AS r MERGE (:IP {address: r.id})",
                {"b": [{"id": ip} for ip in ips[i:i+BATCH]]})

        # 4. SENT_TO relationships
        rows = df[["transaction_id", "sender_account", "receiver_account",
                    "amount", "device_id", "ip_address",
                    "transaction_type", "is_fraud"]].copy()
        rows["timestamp"] = df["timestamp"].astype(str)

        for i in range(0, len(rows), BATCH):
            self.run_write("""
                UNWIND $b AS row
                MATCH (s:Account {account_id: row.sender})
                MATCH (r:Account {account_id: row.receiver})
                CREATE (s)-[t:SENT_TO]->(r)
                SET t.transaction_id   = row.txn_id,
                    t.amount           = row.amount,
                    t.timestamp        = row.timestamp,
                    t.device_id        = row.device_id,
                    t.ip_address       = row.ip_address,
                    t.transaction_type = row.txn_type,
                    t.is_fraud         = row.is_fraud
            """, {"b": [
                {"txn_id":    r.transaction_id,
                 "sender":    r.sender_account,
                 "receiver":  r.receiver_account,
                 "amount":    float(r.amount),
                 "device_id": r.device_id,
                 "ip_address": r.ip_address,
                 "txn_type":  r.transaction_type,
                 "is_fraud":  int(r.is_fraud),
                 "timestamp": r.timestamp}
                for r in rows.iloc[i:i+BATCH].itertuples()
            ]})

        # 5. USED_DEVICE links
        dev_links = df[["sender_account", "device_id"]].drop_duplicates().dropna()
        for i in range(0, len(dev_links), BATCH):
            self.run_write("""
                UNWIND $b AS row
                MATCH (a:Account {account_id: row.src})
                MATCH (d:Device  {device_id:  row.tgt})
                MERGE (a)-[:USED_DEVICE]->(d)
            """, {"b": [{"src": r[0], "tgt": r[1]}
                        for r in dev_links.iloc[i:i+BATCH].itertuples(index=False)]})

        # 6. USED_IP links
        ip_links = df[["sender_account", "ip_address"]].drop_duplicates().dropna()
        for i in range(0, len(ip_links), BATCH):
            self.run_write("""
                UNWIND $b AS row
                MATCH (a:Account {account_id: row.src})
                MATCH (ip:IP     {address:    row.tgt})
                MERGE (a)-[:USED_IP]->(ip)
            """, {"b": [{"src": r[0], "tgt": r[1]}
                        for r in ip_links.iloc[i:i+BATCH].itertuples(index=False)]})

        print(f"  Loaded in {time.time()-t0:.1f}s")
        for row in self.run("MATCH (n) RETURN labels(n)[0] AS l, count(*) AS c"):
            print(f"     {row['l']:<12} {row['c']:>7,} nodes")

    # ── fraud queries ─────────────────────────────────────────────────────────

    def query_rings(self):
        # Variable-length cyclic path queries can expand quickly; cap work early.
        return self.run("""
            MATCH path = (a:Account)-[:SENT_TO*3..5]->(a)
            WHERE ALL(r IN relationships(path) WHERE r.is_fraud = 1)
            WITH path LIMIT 300
            WITH [n IN nodes(path)[0..-1] | n.account_id] AS members,
                 length(path) AS size,
                 reduce(s=0.0, r IN relationships(path) | s + r.amount) AS total
            RETURN members, size, total
            ORDER BY total DESC LIMIT 30
        """)

    def query_chains(self):
        # Prevent path explosion by enforcing node-uniqueness and limiting early.
        return self.run("""
            MATCH path = (s:Account)-[:SENT_TO*4..6]->(e:Account)
            WHERE ALL(r IN relationships(path) WHERE r.is_fraud = 1)
              AND s <> e
              AND ALL(n IN nodes(path) WHERE single(m IN nodes(path) WHERE m = n))
            WITH path, s, e LIMIT 300
            WITH [n IN nodes(path) | n.account_id]      AS chain,
                 [r IN relationships(path) | r.amount]  AS amounts,
                 length(path)                            AS hops,
                 s.account_id AS source, e.account_id AS dest
            RETURN source, dest, chain, amounts, hops
            ORDER BY hops DESC LIMIT 30
        """)

    def query_hubs(self):
        return self.run("""
            MATCH (s:Account)-[t:SENT_TO {is_fraud:1}]->(h:Account)
            WITH h.account_id AS hub,
                 count(DISTINCT s) AS senders,
                 sum(t.amount) AS total,
                 collect(DISTINCT s.account_id)[0..8] AS top_senders
            WHERE senders >= 3
            RETURN hub, senders, total, top_senders
            ORDER BY senders DESC LIMIT 25
        """)

    def query_shared_devices(self):
        return self.run("""
            MATCH (a:Account)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(b:Account)
            WHERE a <> b
            WITH d.device_id AS device,
                 collect(DISTINCT a.account_id)[0..10] AS accounts,
                 count(DISTINCT a) AS cnt
            WHERE cnt >= 2
            RETURN device, accounts, cnt
            ORDER BY cnt DESC LIMIT 20
        """)

    def query_risk_scores(self):
        # Avoid cartesian products from multiple OPTIONAL MATCHes by using subqueries.
        return self.run("""
            MATCH (a:Account)
            CALL {
                WITH a
                MATCH (a)-[o:SENT_TO {is_fraud:1}]->()
                RETURN count(o) AS fraud_sent
            }
            CALL {
                WITH a
                MATCH ()-[i:SENT_TO {is_fraud:1}]->(a)
                RETURN count(i) AS fraud_recv
            }
            CALL {
                WITH a
                MATCH (a)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(b:Account)
                WHERE b <> a
                RETURN count(DISTINCT d) AS shared_dev
            }
            CALL {
                WITH a
                MATCH (a)-[:USED_IP]->(ip:IP)<-[:USED_IP]-(b:Account)
                WHERE b <> a
                RETURN count(DISTINCT ip) AS shared_ip
            }
            WITH a.account_id AS account, fraud_sent, fraud_recv, shared_dev, shared_ip
            WHERE fraud_sent + fraud_recv > 0
            RETURN account, fraud_sent, fraud_recv, shared_dev, shared_ip,
                   (fraud_sent*2 + fraud_recv + shared_dev*3 + shared_ip*2) AS risk_score
            ORDER BY risk_score DESC LIMIT 30
        """)

    def extract_features(self) -> pd.DataFrame:
        rows = self.run("""
        MATCH (a:Account)

        CALL {
            WITH a
            MATCH (a)-[o:SENT_TO]->()
            RETURN count(o) AS out_degree,
                   coalesce(sum(o.amount),0) AS total_sent,
                   coalesce(avg(o.amount),0) AS avg_sent,
                   sum(CASE WHEN o.is_fraud=1 THEN 1 ELSE 0 END) AS fraud_out
        }

        CALL {
            WITH a
            MATCH ()-[i:SENT_TO]->(a)
            RETURN count(i) AS in_degree,
                   coalesce(sum(i.amount),0) AS total_received,
                   sum(CASE WHEN i.is_fraud=1 THEN 1 ELSE 0 END) AS fraud_in
        }

        CALL {
            WITH a
            MATCH (a)-[:USED_DEVICE]->(d:Device)
            RETURN count(DISTINCT d) AS shared_device_count
        }

        CALL {
            WITH a
            MATCH (a)-[:USED_IP]->(ip:IP)
            RETURN count(DISTINCT ip) AS shared_ip_count
        }

        RETURN a.account_id AS account_id,
               out_degree, in_degree, total_sent, total_received,
               avg_sent, shared_device_count, shared_ip_count,
               fraud_out, fraud_in,
               (out_degree + in_degree) AS total_degree
        """)
        return pd.DataFrame(rows)
