# pyre-ignore-all-errors
from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.compat import optional_import, optional_import_attr, records_from_table, read_csv_records, safe_float, safe_int
from core.models import TransactionEvent

pd = optional_import("pandas")

GraphDatabase = optional_import_attr("neo4j", "GraphDatabase")

log = logging.getLogger(__name__)
BATCH_SIZE = 500


def _to_frame(rows: list[dict[str, Any]]) -> Any:
    if pd is None:
        return rows
    return pd.DataFrame(rows)


@dataclass(slots=True)
class GraphInspection:
    score: float
    flags: list[str]
    evidence: dict[str, Any]
    explanation: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "flags": self.flags,
            "evidence": self.evidence,
            "explanation": self.explanation,
        }


class InMemoryFraudGraph:
    """
    Safe local graph backend that does not depend on networkx.
    """

    def __init__(self) -> None:
        self.accounts: set[str] = set()
        self.edges: list[dict[str, Any]] = []
        self.outgoing: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        self.incoming: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        self.account_devices: dict[str, set[str]] = defaultdict(set)
        self.account_ips: dict[str, set[str]] = defaultdict(set)
        self.device_accounts: dict[str, set[str]] = defaultdict(set)
        self.ip_accounts: dict[str, set[str]] = defaultdict(set)

    def clear(self) -> None:
        self.accounts.clear()
        self.edges.clear()
        self.outgoing.clear()
        self.incoming.clear()
        self.account_devices.clear()
        self.account_ips.clear()
        self.device_accounts.clear()
        self.ip_accounts.clear()

    def load(self, frame: Any) -> None:
        for row in records_from_table(frame):
            sender = str(row.get("sender_account", "") or "")
            receiver = str(row.get("receiver_account", "") or "")
            if not sender or not receiver:
                continue
            device_id = str(row.get("device_id", "") or "")
            ip_address = str(row.get("ip_address", "") or "")
            edge = {
                "transaction_id": str(row.get("transaction_id", "") or ""),
                "sender_account": sender,
                "receiver_account": receiver,
                "amount": safe_float(row.get("amount")),
                "timestamp": str(row.get("timestamp", "") or ""),
                "transaction_type": str(row.get("transaction_type", "TRANSFER") or "TRANSFER"),
                "device_id": device_id,
                "ip_address": ip_address,
                "is_fraud": safe_int(row.get("is_fraud")),
            }
            self.accounts.add(sender)
            self.accounts.add(receiver)
            self.edges.append(edge)
            self.outgoing[sender].append((receiver, edge))
            self.incoming[receiver].append((sender, edge))
            if device_id:
                self.account_devices[sender].add(device_id)
                self.device_accounts[device_id].add(sender)
            if ip_address:
                self.account_ips[sender].add(ip_address)
                self.ip_accounts[ip_address].add(sender)

    def seed_from_csv(self, csv_path: str | Path) -> None:
        self.load(read_csv_records(csv_path))

    def _fraud_adjacency(self) -> tuple[dict[str, list[tuple[str, dict[str, Any]]]], dict[str, list[tuple[str, dict[str, Any]]]]]:
        outgoing: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        incoming: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        for edge in self.edges:
            if safe_int(edge.get("is_fraud")) != 1:
                continue
            sender = str(edge["sender_account"])
            receiver = str(edge["receiver_account"])
            outgoing[sender].append((receiver, edge))
            incoming[receiver].append((sender, edge))
        return outgoing, incoming

    @staticmethod
    def _canonical_cycle(nodes: list[str]) -> tuple[str, ...]:
        rotations = [tuple(nodes[index:] + nodes[:index]) for index in range(len(nodes))] # type: ignore
        return min(rotations)

    @staticmethod
    def _reachable(start: str, adjacency: dict[str, list[tuple[str, dict[str, Any]]]]) -> set[str]:
        seen: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(neighbour for neighbour, _ in adjacency.get(node, []))
        return seen

    def query_rings(self, limit: int = 30) -> list[dict[str, Any]]:
        outgoing, _ = self._fraud_adjacency()
        rings: dict[tuple[str, ...], dict[str, Any]] = {}

        def walk(start: str, node: str, path: list[str], amounts: list[float], seen: set[str]) -> None:
            for neighbour, edge in outgoing.get(node, []):
                amount = safe_float(edge.get("amount"))
                if neighbour == start and 3 <= len(path) <= 5:
                    members = self._canonical_cycle(path.copy())
                    total = round(float(sum(amounts) + amount), 2) # type: ignore
                    current = rings.get(members)
                    if current is None or total > current["total"]:
                        rings[members] = {"members": list(members), "size": len(members), "total": total}
                    continue
                if neighbour in seen or len(path) >= 5:
                    continue
                seen.add(neighbour)
                path.append(neighbour)
                amounts.append(amount)
                walk(start, neighbour, path, amounts, seen)
                amounts.pop()
                path.pop()
                seen.remove(neighbour)

        for start in sorted(outgoing):
            walk(start, start, [start], [], {start})
        return sorted(rings.values(), key=lambda item: (item["total"], item["size"]), reverse=True)[:limit]

    def query_chains(self, limit: int = 30) -> list[dict[str, Any]]:
        outgoing, _ = self._fraud_adjacency()
        chains: dict[tuple[str, ...], dict[str, Any]] = {}

        def walk(node: str, path: list[str], amounts: list[float]) -> None:
            hops = len(path) - 1
            if 4 <= hops <= 6:
                key = tuple(path)
                chains[key] = {
                    "source": path[0],
                    "dest": path[-1],
                    "chain": path.copy(),
                    "amounts": amounts.copy(),
                    "hops": hops,
                }
            if hops == 6:
                return
            for neighbour, edge in outgoing.get(node, []):
                if neighbour in path:
                    continue
                path.append(neighbour)
                amounts.append(safe_float(edge.get("amount")))
                walk(neighbour, path, amounts)
                amounts.pop()
                path.pop()

        for start in sorted(outgoing):
            walk(start, [start], [])
        ordered = sorted(chains.values(), key=lambda item: (item["hops"], sum(item["amounts"])), reverse=True)
        return ordered[:limit]

    def query_hubs(self, limit: int = 25) -> list[dict[str, Any]]:
        _, incoming = self._fraud_adjacency()
        hubs: list[dict[str, Any]] = []
        for node, edges in incoming.items():
            unique_senders = sorted({source for source, _ in edges})
            if len(unique_senders) >= 3:
                total = round(sum(safe_float(edge.get("amount")) for _, edge in edges), 2)
                hubs.append(
                    {
                        "hub": node,
                        "senders": len(unique_senders),
                        "total": total,
                        "top_senders": unique_senders[:8],
                    }
                )
        hubs.sort(key=lambda item: item["senders"], reverse=True)
        return hubs[:limit]

    def query_shared_devices(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = []
        for device_id, accounts in self.device_accounts.items():
            if len(accounts) >= 2:
                rows.append({"device": device_id, "accounts": sorted(accounts)[:10], "cnt": len(accounts)})
        rows.sort(key=lambda item: item["cnt"], reverse=True)
        return rows[:limit]

    def query_risk_scores(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = []
        for account in sorted(self.accounts):
            fraud_sent = sum(1 for _, edge in self.outgoing.get(account, []) if safe_int(edge.get("is_fraud")) == 1)
            fraud_recv = sum(1 for _, edge in self.incoming.get(account, []) if safe_int(edge.get("is_fraud")) == 1)
            shared_dev = sum(
                1 for device_id in self.account_devices.get(account, set()) if len(self.device_accounts.get(device_id, set())) > 1
            )
            shared_ip = sum(1 for ip in self.account_ips.get(account, set()) if len(self.ip_accounts.get(ip, set())) > 1)
            risk_score = fraud_sent * 2 + fraud_recv + shared_dev * 3 + shared_ip * 2
            if risk_score > 0:
                rows.append(
                    {
                        "account": account,
                        "fraud_sent": fraud_sent,
                        "fraud_recv": fraud_recv,
                        "shared_dev": shared_dev,
                        "shared_ip": shared_ip,
                        "risk_score": risk_score,
                    }
                )
        rows.sort(key=lambda item: item["risk_score"], reverse=True)
        return rows[:limit]

    def extract_features(self) -> Any:
        rows = []
        for account in sorted(self.accounts):
            outgoing = self.outgoing.get(account, [])
            incoming = self.incoming.get(account, [])
            total_sent = sum(safe_float(edge.get("amount")) for _, edge in outgoing)
            total_received = sum(safe_float(edge.get("amount")) for _, edge in incoming)
            fraud_out = sum(safe_int(edge.get("is_fraud")) for _, edge in outgoing)
            fraud_in = sum(safe_int(edge.get("is_fraud")) for _, edge in incoming)
            rows.append(
                {
                    "account_id": account,
                    "out_degree": len(outgoing),
                    "in_degree": len(incoming),
                    "total_sent": total_sent,
                    "total_received": total_received,
                    "avg_sent": total_sent / max(len(outgoing), 1),
                    "shared_device_count": len(self.account_devices.get(account, set())),
                    "shared_ip_count": len(self.account_ips.get(account, set())),
                    "fraud_out": fraud_out,
                    "fraud_in": fraud_in,
                    "total_degree": len(outgoing) + len(incoming),
                }
            )
        return _to_frame(rows)

    def inspect_transaction(self, event: TransactionEvent) -> GraphInspection:
        outgoing, incoming = self._fraud_adjacency()
        sender = event.sender_account
        receiver = event.receiver_account
        device_accounts = sorted(self.device_accounts.get(event.device_id, set()) - {sender})
        ip_accounts = sorted(self.ip_accounts.get(event.ip_address, set()) - {sender})
        receiver_incoming = len({source for source, _ in incoming.get(receiver, [])})

        sender_scc_size = 0
        if sender in self.accounts:
            reachable = self._reachable(sender, outgoing)
            reverse_reachable = self._reachable(sender, incoming)
            sender_scc_size = len(reachable & reverse_reachable)

        mule_chain_length = 0

        def walk_chain(node: str, path: list[str]) -> None:
            nonlocal mule_chain_length
            hops = len(path) - 1
            if 2 <= hops <= 4:
                mule_chain_length = max(mule_chain_length, hops)
            if hops == 4:
                return
            for neighbour, _ in outgoing.get(node, []):
                if neighbour in path:
                    continue
                path.append(neighbour)
                walk_chain(neighbour, path)
                path.pop()

        if receiver in outgoing:
            walk_chain(receiver, [receiver])

        flags: list[str] = []
        explanation: list[str] = []
        score = 0.0

        if device_accounts:
            flags.append("SHARED_DEVICE")
            score += min(0.12 * len(device_accounts), 0.24)
            explanation.append(f"device {event.device_id} is shared by {len(device_accounts) + 1} accounts")
        if ip_accounts:
            flags.append("SHARED_IP")
            score += min(0.08 * len(ip_accounts), 0.16)
            explanation.append(f"ip {event.ip_address} is shared across {len(ip_accounts) + 1} accounts")
        if receiver_incoming >= 2:
            flags.append("MULE_HUB")
            score += min(0.1 * receiver_incoming, 0.25)
            explanation.append(f"receiver {receiver} already receives suspicious flows from {receiver_incoming} accounts")
        if mule_chain_length >= 2:
            flags.append("MULE_CHAIN")
            score += 0.25
            explanation.append(f"receiver {receiver} links to a {mule_chain_length}-hop fraud chain")
        if sender_scc_size >= 3:
            flags.append("FRAUD_RING")
            score += 0.22
            explanation.append(f"sender {sender} belongs to a {sender_scc_size}-node ring")

        return GraphInspection(
            score=round(min(score, 0.99), 4),
            flags=flags,
            evidence={
                "shared_device_accounts": device_accounts[:8],
                "shared_ip_accounts": ip_accounts[:8],
                "receiver_fraud_in_degree": receiver_incoming,
                "mule_chain_length": mule_chain_length,
                "ring_member_count": sender_scc_size,
            },
            explanation=explanation,
        )


class Neo4jFraudGraph:
    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        if GraphDatabase is None:
            raise RuntimeError("neo4j driver is not installed")
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "frauddetection123")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def __enter__(self) -> "Neo4jFraudGraph":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.driver.close()

    def run(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        for attempt in range(3):
            try:
                with self.driver.session() as session:
                    return session.run(cypher, params or {}).data()
            except Exception as e:
                log.warning("Neo4j transient read error: %s. Retrying %d/3...", e, attempt + 1)
                if attempt == 2:
                    raise
                import time
                time.sleep(1.0 * (attempt + 1))
        return []

    def run_write(self, cypher: str, params: dict[str, Any] | None = None) -> None:
        for attempt in range(3):
            try:
                with self.driver.session() as session:
                    session.execute_write(lambda tx: list(tx.run(cypher, params or {})))
                    return
            except Exception as e:
                log.warning("Neo4j transient write error: %s. Retrying %d/3...", e, attempt + 1)
                if attempt == 2:
                    raise
                import time
                time.sleep(1.0 * (attempt + 1))

    def clear(self) -> None:
        self.run_write("MATCH (n) DETACH DELETE n")

    def setup_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT account_id IF NOT EXISTS FOR (a:Account) REQUIRE a.account_id IS UNIQUE",
            "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (d:Device) REQUIRE d.device_id IS UNIQUE",
            "CREATE CONSTRAINT ip_address IF NOT EXISTS FOR (i:IP) REQUIRE i.address IS UNIQUE",
        ]
        for statement in statements:
            self.run_write(statement)

    def load(self, frame: Any) -> None:
        rows = []
        for record in records_from_table(frame):
            rows.append(
                {
                    "transaction_id": str(record.get("transaction_id", "") or ""),
                    "sender": str(record.get("sender_account", "") or ""),
                    "receiver": str(record.get("receiver_account", "") or ""),
                    "amount": safe_float(record.get("amount")),
                    "timestamp": str(record.get("timestamp", "") or ""),
                    "transaction_type": str(record.get("transaction_type", "TRANSFER") or "TRANSFER"),
                    "device_id": str(record.get("device_id", "") or ""),
                    "ip_address": str(record.get("ip_address", "") or ""),
                    "is_fraud": safe_int(record.get("is_fraud")),
                }
            )

        accounts = sorted({row["sender"] for row in rows}.union({row["receiver"] for row in rows}))
        for index in range(0, len(accounts), BATCH_SIZE):
            batch = [{"id": account} for account in accounts[index:index + BATCH_SIZE] if account]
            if batch:
                self.run_write("UNWIND $batch AS row MERGE (:Account {account_id: row.id})", {"batch": batch})

        devices = sorted({row["device_id"] for row in rows if row["device_id"]})
        for index in range(0, len(devices), BATCH_SIZE):
            batch = [{"id": device} for device in devices[index:index + BATCH_SIZE]]
            self.run_write("UNWIND $batch AS row MERGE (:Device {device_id: row.id})", {"batch": batch})

        ips = sorted({row["ip_address"] for row in rows if row["ip_address"]})
        for index in range(0, len(ips), BATCH_SIZE):
            batch = [{"id": ip} for ip in ips[index:index + BATCH_SIZE]]
            self.run_write("UNWIND $batch AS row MERGE (:IP {address: row.id})", {"batch": batch})

        for index in range(0, len(rows), BATCH_SIZE):
            batch = rows[index:index + BATCH_SIZE]
            self.run_write(
                """
                UNWIND $batch AS row
                MATCH (sender:Account {account_id: row.sender})
                MATCH (receiver:Account {account_id: row.receiver})
                CREATE (sender)-[txn:SENT_TO]->(receiver)
                SET txn.transaction_id = row.transaction_id,
                    txn.amount = row.amount,
                    txn.timestamp = row.timestamp,
                    txn.transaction_type = row.transaction_type,
                    txn.device_id = row.device_id,
                    txn.ip_address = row.ip_address,
                    txn.is_fraud = row.is_fraud
                FOREACH (_ IN CASE WHEN row.device_id = '' THEN [] ELSE [1] END |
                    MERGE (device:Device {device_id: row.device_id})
                    MERGE (sender)-[:USED_DEVICE]->(device))
                FOREACH (_ IN CASE WHEN row.ip_address = '' THEN [] ELSE [1] END |
                    MERGE (ip:IP {address: row.ip_address})
                    MERGE (sender)-[:USED_IP]->(ip))
                """,
                {"batch": batch},
            )

    def seed_from_csv(self, csv_path: str | Path, clear_existing: bool = False) -> None:
        rows = read_csv_records(csv_path)
        if clear_existing:
            self.clear()
        self.setup_schema()
        self.load(rows)

    def query_rings(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.run(
            """
            MATCH path = (a:Account)-[:SENT_TO*3..4]->(a)
            WHERE ALL(rel IN relationships(path) WHERE rel.is_fraud = 1)
            WITH path LIMIT 400
            RETURN [node IN nodes(path)[0..-1] | node.account_id] AS members,
                   length(path) AS size,
                   reduce(total = 0.0, rel IN relationships(path) | total + rel.amount) AS total
            ORDER BY total DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def query_chains(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.run(
            """
            MATCH path = (source:Account)-[:SENT_TO*3..5]->(dest:Account)
            WHERE source <> dest
              AND ALL(rel IN relationships(path) WHERE rel.is_fraud = 1)
              AND ALL(node IN nodes(path) WHERE single(other IN nodes(path) WHERE other = node))
            WITH path, source, dest LIMIT 400
            RETURN source.account_id AS source,
                   dest.account_id AS dest,
                   [node IN nodes(path) | node.account_id] AS chain,
                   [rel IN relationships(path) | rel.amount] AS amounts,
                   length(path) AS hops
            ORDER BY hops DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def query_hubs(self, limit: int = 25) -> list[dict[str, Any]]:
        return self.run(
            """
            MATCH (sender:Account)-[txn:SENT_TO {is_fraud: 1}]->(hub:Account)
            WITH hub,
                 count(DISTINCT sender) AS senders,
                 sum(txn.amount) AS total,
                 collect(DISTINCT sender.account_id)[0..8] AS top_senders
            WHERE senders >= 3
            RETURN hub.account_id AS hub, senders, total, top_senders
            ORDER BY senders DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def query_shared_devices(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.run(
            """
            MATCH (a:Account)-[:USED_DEVICE]->(device:Device)<-[:USED_DEVICE]-(b:Account)
            WHERE a <> b
            WITH device,
                 collect(DISTINCT a.account_id)[0..10] AS accounts,
                 count(DISTINCT a) AS cnt
            WHERE cnt >= 2
            RETURN device.device_id AS device, accounts, cnt
            ORDER BY cnt DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def query_risk_scores(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.run(
            """
            MATCH (a:Account)
            CALL {
                WITH a
                MATCH (a)-[sent:SENT_TO {is_fraud: 1}]->()
                RETURN count(sent) AS fraud_sent
            }
            CALL {
                WITH a
                MATCH ()-[recv:SENT_TO {is_fraud: 1}]->(a)
                RETURN count(recv) AS fraud_recv
            }
            CALL {
                WITH a
                MATCH (a)-[:USED_DEVICE]->(device:Device)<-[:USED_DEVICE]-(other:Account)
                WHERE other <> a
                RETURN count(DISTINCT device) AS shared_dev
            }
            CALL {
                WITH a
                MATCH (a)-[:USED_IP]->(ip:IP)<-[:USED_IP]-(other:Account)
                WHERE other <> a
                RETURN count(DISTINCT ip) AS shared_ip
            }
            WITH a.account_id AS account, fraud_sent, fraud_recv, shared_dev, shared_ip
            WHERE fraud_sent + fraud_recv + shared_dev + shared_ip > 0
            RETURN account, fraud_sent, fraud_recv, shared_dev, shared_ip,
                   fraud_sent * 2 + fraud_recv + shared_dev * 3 + shared_ip * 2 AS risk_score
            ORDER BY risk_score DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def extract_features(self) -> Any:
        rows = self.run(
            """
            MATCH (a:Account)
            CALL {
                WITH a
                MATCH (a)-[sent:SENT_TO]->()
                RETURN count(sent) AS out_degree,
                       coalesce(sum(sent.amount), 0.0) AS total_sent,
                       coalesce(avg(sent.amount), 0.0) AS avg_sent,
                       sum(CASE WHEN sent.is_fraud = 1 THEN 1 ELSE 0 END) AS fraud_out
            }
            CALL {
                WITH a
                MATCH ()-[recv:SENT_TO]->(a)
                RETURN count(recv) AS in_degree,
                       coalesce(sum(recv.amount), 0.0) AS total_received,
                       sum(CASE WHEN recv.is_fraud = 1 THEN 1 ELSE 0 END) AS fraud_in
            }
            CALL {
                WITH a
                MATCH (a)-[:USED_DEVICE]->(device:Device)
                RETURN count(DISTINCT device) AS shared_device_count
            }
            CALL {
                WITH a
                MATCH (a)-[:USED_IP]->(ip:IP)
                RETURN count(DISTINCT ip) AS shared_ip_count
            }
            RETURN a.account_id AS account_id,
                   out_degree,
                   in_degree,
                   total_sent,
                   total_received,
                   avg_sent,
                   shared_device_count,
                   shared_ip_count,
                   fraud_out,
                   fraud_in,
                   out_degree + in_degree AS total_degree
            """
        )
        return _to_frame(rows)

    def inspect_transaction(self, event: TransactionEvent) -> GraphInspection:
        shared_device_rows = self.run(
            """
            MATCH (:Account {account_id: $sender})-[:USED_DEVICE]->(device:Device {device_id: $device})<-[:USED_DEVICE]-(other:Account)
            WHERE other.account_id <> $sender
            RETURN collect(other.account_id)[0..8] AS accounts, count(DISTINCT other) AS cnt
            """,
            {"sender": event.sender_account, "device": event.device_id},
        )
        shared_ip_rows = self.run(
            """
            MATCH (:Account {account_id: $sender})-[:USED_IP]->(ip:IP {address: $ip})<-[:USED_IP]-(other:Account)
            WHERE other.account_id <> $sender
            RETURN collect(other.account_id)[0..8] AS accounts, count(DISTINCT other) AS cnt
            """,
            {"sender": event.sender_account, "ip": event.ip_address},
        )
        ring_rows = self.run(
            """
            MATCH path = (a:Account {account_id: $sender})-[:SENT_TO*3..5]->(a)
            WHERE ALL(rel IN relationships(path) WHERE rel.is_fraud = 1)
            RETURN length(path) AS hops
            LIMIT 1
            """,
            {"sender": event.sender_account},
        )
        mule_rows = self.run(
            """
            MATCH path = (receiver:Account {account_id: $receiver})-[:SENT_TO*2..4]->(:Account)
            WHERE ALL(rel IN relationships(path) WHERE rel.is_fraud = 1)
            RETURN max(length(path)) AS hops
            """,
            {"receiver": event.receiver_account},
        )
        hub_rows = self.run(
            """
            MATCH (sender:Account)-[:SENT_TO {is_fraud: 1}]->(receiver:Account {account_id: $receiver})
            RETURN count(DISTINCT sender) AS cnt
            """,
            {"receiver": event.receiver_account},
        )

        shared_device_cnt = int(shared_device_rows[0]["cnt"]) if shared_device_rows else 0
        shared_ip_cnt = int(shared_ip_rows[0]["cnt"]) if shared_ip_rows else 0
        ring_hops = int(ring_rows[0]["hops"]) if ring_rows else 0
        mule_hops = int(mule_rows[0]["hops"]) if mule_rows and mule_rows[0]["hops"] else 0
        receiver_hub_cnt = int(hub_rows[0]["cnt"]) if hub_rows else 0

        flags: list[str] = []
        explanation: list[str] = []
        score = 0.0
        if shared_device_cnt:
            flags.append("SHARED_DEVICE")
            score += min(0.12 * shared_device_cnt, 0.24)
            explanation.append(f"device reused by {shared_device_cnt + 1} linked accounts")
        if shared_ip_cnt:
            flags.append("SHARED_IP")
            score += min(0.08 * shared_ip_cnt, 0.16)
            explanation.append(f"ip reused by {shared_ip_cnt + 1} linked accounts")
        if receiver_hub_cnt >= 2:
            flags.append("MULE_HUB")
            score += min(0.1 * receiver_hub_cnt, 0.25)
            explanation.append(f"receiver already connected to {receiver_hub_cnt} suspicious inbound transfers")
        if mule_hops >= 2:
            flags.append("MULE_CHAIN")
            score += 0.25
            explanation.append(f"receiver extends a {mule_hops}-hop mule chain")
        if ring_hops >= 3:
            flags.append("FRAUD_RING")
            score += 0.22
            explanation.append("sender participates in a cyclic fraud ring")

        return GraphInspection(
            score=round(min(score, 0.99), 4),
            flags=flags,
            evidence={
                "shared_device_accounts": shared_device_rows[0]["accounts"] if shared_device_rows else [],
                "shared_ip_accounts": shared_ip_rows[0]["accounts"] if shared_ip_rows else [],
                "receiver_fraud_in_degree": receiver_hub_cnt,
                "mule_chain_length": mule_hops,
                "ring_member_count": ring_hops,
            },
            explanation=explanation,
        )


def build_graph_backend(use_neo4j: bool = False, **kwargs: Any) -> Neo4jFraudGraph | InMemoryFraudGraph:
    if use_neo4j:
        try:
            return Neo4jFraudGraph(
                uri=kwargs.get("uri"),
                user=kwargs.get("user"),
                password=kwargs.get("password"),
            )
        except Exception as exc:  # pragma: no cover - depends on local infra
            log.warning("Falling back to in-memory graph because Neo4j is unavailable: %s", exc)
    return InMemoryFraudGraph()
