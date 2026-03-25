from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from core.compat import optional_import, optional_import_attr, records_from_table

joblib = optional_import("joblib")
pd = optional_import("pandas")
GradientBoostingClassifier = optional_import_attr("sklearn.ensemble", "GradientBoostingClassifier")
XGBClassifier = optional_import_attr("xgboost", "XGBClassifier")


FEATURE_ORDER = [
    "transaction_monitor",
    "behaviour_analyser",
    "graph_fraud_detector",
    "amount_scaled",
    "device_mismatch",
    "new_beneficiary",
    "geo_velocity_scaled",
    "login_velocity_scaled",
]


class CompositeRiskModel:
    def __init__(self, model_dir: str | Path) -> None:
        self.model_dir = Path(model_dir)
        self.model_path = self.model_dir / "xgboost_risk_model.joblib"
        self.metadata_path = self.model_dir / "xgboost_risk_model.metadata.json"
        self.model = None
        self.model_name = "heuristic-fallback"
        if self.model_path.exists() and joblib is not None:
            try:
                self.model = joblib.load(self.model_path)
            except Exception:
                self.model = None
            else:
                self.model_name = type(self.model).__name__

    def _build_model(self) -> Any:
        if XGBClassifier is not None:
            self.model_name = "xgboost"
            return XGBClassifier(
                n_estimators=160,
                max_depth=4,
                learning_rate=0.08,
                subsample=0.9,
                colsample_bytree=0.9,
                eval_metric="logloss",
                random_state=42,
            )
        if GradientBoostingClassifier is not None:
            self.model_name = "gradient-boosting-fallback"
            return GradientBoostingClassifier(random_state=42)
        self.model_name = "heuristic-fallback"
        return None

    def fit(self, frame: Any, target_column: str) -> None:
        rows = records_from_table(frame)
        if not rows:
            return
        if pd is None:
            self._write_metadata()
            return

        train_rows: list[dict[str, float | int]] = []
        for row in rows:
            record = {name: float(row.get(name, 0.0) or 0.0) for name in FEATURE_ORDER}
            record[target_column] = int(float(row.get(target_column, 0) or 0))
            train_rows.append(record)

        targets = [int(row[target_column]) for row in train_rows]
        if len(set(targets)) < 2:
            self.model = None
            self.model_name = "heuristic-fallback"
            self._write_metadata()
            return

        model = self._build_model()
        if model is None:
            self._write_metadata()
            return

        features = pd.DataFrame([{name: row[name] for name in FEATURE_ORDER} for row in train_rows], columns=FEATURE_ORDER)
        target = pd.Series(targets, dtype=int)
        model.fit(features, target)
        self.model = model
        if joblib is not None:
            try:
                joblib.dump(self.model, self.model_path)
            except Exception:
                pass
        self._write_metadata()

    def predict_components(self, feature_vector: dict[str, float]) -> dict[str, float | None]:
        heuristic_score = round(self._heuristic_score(feature_vector), 4)
        learned_score: float | None = None
        if self.model is not None and pd is not None:
            try:
                frame = pd.DataFrame([[feature_vector.get(name, 0.0) for name in FEATURE_ORDER]], columns=FEATURE_ORDER)
                learned_score = round(float(self.model.predict_proba(frame)[0, 1]), 4)
            except Exception:
                learned_score = None

        # Safety rule: a weakly calibrated trained model must not suppress
        # strong agent evidence in obvious fraud scenarios.
        final_score = heuristic_score if learned_score is None else max(learned_score, heuristic_score)
        return {
            "heuristic_score": heuristic_score,
            "learned_score": learned_score,
            "final_score": round(final_score, 4),
        }

    def predict_score(self, feature_vector: dict[str, float]) -> float:
        return float(self.predict_components(feature_vector)["final_score"])

    def _heuristic_score(self, feature_vector: dict[str, float]) -> float:
        weighted_sum = (
            2.2 * feature_vector.get("transaction_monitor", 0.0)
            + 2.0 * feature_vector.get("behaviour_analyser", 0.0)
            + 2.4 * feature_vector.get("graph_fraud_detector", 0.0)
            + 1.2 * feature_vector.get("device_mismatch", 0.0)
            + 0.9 * feature_vector.get("new_beneficiary", 0.0)
            + 1.1 * feature_vector.get("geo_velocity_scaled", 0.0)
            + 0.7 * feature_vector.get("login_velocity_scaled", 0.0)
            + 0.5 * feature_vector.get("amount_scaled", 0.0)
            - 2.4
        )
        return 1.0 / (1.0 + math.exp(-weighted_sum))

    def _write_metadata(self) -> None:
        payload = {"model_name": self.model_name, "features": FEATURE_ORDER}
        self.metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
