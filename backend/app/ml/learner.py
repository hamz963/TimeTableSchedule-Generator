"""Train (and re-train) the teacher-preference model on feedback."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "preference_model.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"


def _default_paths():
    """Model location; ML_MODEL_DIR lets deployments share files via a volume."""
    from app.config import get_settings

    custom = (get_settings().ml_model_dir or "").strip()
    base = Path(custom) if custom else Path(__file__).resolve().parent / "models"
    return base, base / "preference_model.pkl", base / "scaler.pkl"


MODEL_DIR, MODEL_PATH, SCALER_PATH = _default_paths()

MIN_SAMPLES = 30  # per product spec: learning starts at 30 feedback responses


def train_model(db) -> Dict[str, Any]:
    """Train RandomForest on all feedback; persist model + registry row."""
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    from app.ml.features import build_training_rows
    from app.models.feedback import MLModel

    X, y, skipped = build_training_rows(db)
    if len(X) < MIN_SAMPLES:
        return {
            "trained": False,
            "reason": f"need at least {MIN_SAMPLES} usable feedback rows, have {len(X)}",
            "samples": len(X),
            "skipped": skipped,
        }

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    if len(X) >= 10:
        X_train, X_test, y_train, y_test = train_test_split(
            Xs, y, test_size=0.2, random_state=42
        )
    else:  # tiny data: evaluate on train (reported honestly in params)
        X_train, X_test, y_train, y_test = Xs, Xs, y, y

    model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
    model.fit(X_train, y_train)
    accuracy = float(model.score(X_test, y_test))
    evaluated_on = "held_out_20pct" if len(X) >= 10 else "train_set_tiny_data"

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)

    latest = db.query(MLModel).order_by(MLModel.version.desc()).first()
    version = (latest.version + 1) if latest else 1
    db.add(
        MLModel(
            version=version,
            trained_at=datetime.now(timezone.utc),
            training_samples=len(X),
            accuracy=accuracy,
            params={"evaluated_on": evaluated_on, "skipped_rows": skipped},
        )
    )
    db.commit()
    return {
        "trained": True,
        "version": version,
        "samples": len(X),
        "skipped": skipped,
        "accuracy": round(accuracy, 4),
        "evaluated_on": evaluated_on,
    }
