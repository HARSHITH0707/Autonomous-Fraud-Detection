from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import NetworkSettings
from services import DataStrategy
from ml_models.model_service import CompositeRiskModel


def main() -> None:
    settings = NetworkSettings()
    strategy = DataStrategy(settings)
    frame = strategy.supervised_training_frame(max_rows=15000)
    if frame.empty:
        print("IEEE-CIS training data not found. Skipping.")
        return

    model = CompositeRiskModel(settings.model_dir)
    model.fit(frame, "is_fraud")
    print(f"trained {model.model_name} risk model on {len(frame):,} labelled rows")


if __name__ == "__main__":
    main()
