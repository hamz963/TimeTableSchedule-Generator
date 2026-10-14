"""ML package: learn teacher time-of-day preferences from feedback."""
from app.ml.features import FEATURE_NAMES, build_training_rows, teacher_schedule_features
from app.ml.learner import MODEL_DIR, train_model
from app.ml.predictor import suggest_preferences

__all__ = [
    "FEATURE_NAMES",
    "MODEL_DIR",
    "build_training_rows",
    "teacher_schedule_features",
    "train_model",
    "suggest_preferences",
]
