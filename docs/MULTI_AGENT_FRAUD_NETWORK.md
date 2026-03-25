# Multi-Agent Fraud Detection Network Design

## Architecture Summary

The target architecture is a fan-out/fan-in fraud pipeline:

- Fan-out from `txn.raw` to transaction, behaviour, and graph agents.
- Fan-in at the risk scorer.
- Centralized decisioning at the response engine.
- Persistent audit and compliance logging after the response path is resolved.

## Scalability Model

- Each agent is stateless or state-light enough to scale horizontally behind Kafka consumer groups.
- Behaviour profiles and model artefacts are externalizable to Redis, feature stores, or object storage.
- Neo4j is isolated behind the graph detector so relationship detection can scale independently from transaction scoring.
- The MCP layer is only the orchestration boundary. It is not on the hot path between internal agents in production deployments.

## Fault Tolerance

- Kafka decouples producers and consumers and supports replay after transient failures.
- Agent outputs are idempotent by `transaction_id`.
- Compliance artefacts are written separately from the decision path so a logging failure does not force an allow decision.
- The local in-memory broker is only for simulation; production should use Kafka with replicated topics.

## Real-World Scenario

Scenario:

1. A customer logs in from the UAE using an unseen burner device.
2. Minutes later a large UPI transfer is initiated to a brand-new beneficiary.
3. The graph detector finds the beneficiary in a mule chain already tied to shared devices and suspicious inbound paths.
4. The risk scorer combines transaction, behaviour, and graph evidence into a high composite risk.
5. The decision engine blocks the payment and returns an API callback payload in milliseconds.
6. The compliance logger stores forensic evidence and report-ready records.

Expected scoring pattern:

- Transaction Monitor: high because of amount, velocity, and new beneficiary
- Behaviour Analyser: high because of foreign login, device mismatch, geo drift, and login burst
- Graph Fraud Detector: high because of mule-chain and shared-device evidence
- Final composite score: above the block threshold

## Dataset Role Mapping

- IEEE-CIS:
  labelled historical fraud for supervised XGBoost training
- PaySim:
  high-volume synthetic payment activity for stream replay and latency testing
- Synthetic graph data:
  deterministic fraud-ring and mule-chain structures to validate graph traversal logic
