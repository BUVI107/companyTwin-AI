"""
Company Fit Predictor.

A small RandomForestRegressor trained on a synthetic-but-realistic
dataset of (skill_match_pct, avg_response_time, avg_sentiment,
confidence_score) -> fit_score (0-100).

For your report: in a real deployment you'd replace generate_training_data()
with a labeled dataset built from real interview outcomes. Here we simulate
that dataset with a clear, explainable rule + noise, which is a standard and
defensible approach for a final-year ML component when historical data
doesn't exist yet.
"""
import os
import numpy as np
import joblib
from sklearn.ensemble import RandomForestRegressor

MODEL_PATH = os.path.join(os.path.dirname(__file__), "fit_model.joblib")
_model = None


def generate_training_data(n=400, seed=42):
    rng = np.random.default_rng(seed)
    skill_match = rng.uniform(0, 100, n)
    response_time = rng.uniform(5, 90, n)
    sentiment = rng.uniform(-1, 1, n)
    confidence = rng.uniform(0, 100, n)

    # Ground-truth rule used to generate labels (+ noise), so the model
    # has something meaningful to learn instead of pure random labels.
    speed_penalty = np.abs(response_time - 30) * 0.3
    fit = (
        0.45 * skill_match
        + 0.25 * confidence
        + 0.15 * ((sentiment + 1) / 2 * 100)
        - speed_penalty
        + rng.normal(0, 5, n)
    )
    fit = np.clip(fit, 0, 100)

    X = np.column_stack([skill_match, response_time, sentiment, confidence])
    y = fit
    return X, y


def train_and_save():
    X, y = generate_training_data()
    model = RandomForestRegressor(n_estimators=150, max_depth=8, random_state=42)
    model.fit(X, y)
    joblib.dump(model, MODEL_PATH)
    return model


def _get_model():
    global _model
    if _model is not None:
        return _model
    if os.path.exists(MODEL_PATH):
        _model = joblib.load(MODEL_PATH)
    else:
        _model = train_and_save()
    return _model


def predict_fit(skill_match_pct, avg_response_time, avg_sentiment, confidence_score):
    model = _get_model()
    X = np.array([[skill_match_pct, avg_response_time, avg_sentiment, confidence_score]])
    pred = model.predict(X)[0]
    return round(float(np.clip(pred, 0, 100)), 1)


if __name__ == "__main__":
    train_and_save()
    print(f"Model trained and saved to {MODEL_PATH}")
