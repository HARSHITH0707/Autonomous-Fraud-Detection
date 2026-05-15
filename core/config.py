from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _root_path() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class NetworkSettings:
    root_dir: Path = field(default_factory=_root_path)
    data_dir: Path = field(init=False)
    output_dir: Path = field(init=False)
    model_dir: Path = field(init=False)
    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "frauddetection123"))
    kafka_bootstrap_servers: str = field(default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
    kafka_client_id: str = field(default_factory=lambda: os.getenv("KAFKA_CLIENT_ID", "fraud-network"))
    use_neo4j: bool = field(default_factory=lambda: os.getenv("USE_NEO4J", "false").lower() == "true")
    decision_block_threshold: float = field(default_factory=lambda: float(os.getenv("BLOCK_THRESHOLD", "0.8")))
    decision_otp_threshold: float = field(default_factory=lambda: float(os.getenv("OTP_THRESHOLD", "0.55")))
    mongodb_uri: str = field(default_factory=lambda: os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    mongodb_db: str = field(default_factory=lambda: os.getenv("MONGODB_DB", "fraud_detection"))
    firebase_project_id: str = field(default_factory=lambda: os.getenv("FIREBASE_PROJECT_ID", ""))

    def __post_init__(self) -> None:
        self.data_dir = Path(os.getenv("DATA_DIR", self.root_dir / "data"))
        self.output_dir = Path(os.getenv("OUTPUT_DIR", self.root_dir / "outputs"))
        self.model_dir = Path(os.getenv("MODEL_DIR", self.root_dir / "ml_models"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)
