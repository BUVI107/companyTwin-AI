"""
Behavioral analysis + scoring for a completed interview session.

- Sentiment/confidence scoring on each answer (TextBlob).
- Aggregate technical / HR sub-scores.
- ML-based "Company Fit Score" via core/ml/fit_predictor.py.
"""
from textblob import TextBlob
from .ml.fit_predictor import predict_fit


def score_response(answer_text: str, response_time_seconds: float):
    """Return (sentiment_score, confidence_score) for one answer."""
    if not answer_text.strip():
        return 0.0, 0.0

    blob = TextBlob(answer_text)
    sentiment = round(blob.sentiment.polarity, 3)  # -1..1

    # Confidence heuristic: longer, more decisive answers, answered
    # in a reasonable time window, score higher. This is intentionally
    # simple/explainable for a final-year viva.
    word_count = len(answer_text.split())
    length_component = min(word_count / 60, 1.0) * 40          # up to 40 pts
    speed_component = max(0, 1 - abs(response_time_seconds - 30) / 60) * 30  # up to 30 pts
    sentiment_component = (sentiment + 1) / 2 * 30              # up to 30 pts

    confidence = round(length_component + speed_component + sentiment_component, 1)
    return sentiment, min(confidence, 100.0)


def compute_session_score(session):
    """Aggregate all Response rows for a session into a SessionScore."""
    from .models import SessionScore

    responses = list(session.responses.all())
    if not responses:
        return None

    technical = [r for r in responses if r.persona_type == "technical"]
    hr = [r for r in responses if r.persona_type in ("hr", "manager")]

    technical_score = _avg([r.confidence_score for r in technical])
    hr_score = _avg([r.confidence_score for r in hr])
    confidence_score = _avg([r.confidence_score for r in responses])
    avg_response_time = _avg([r.response_time_seconds for r in responses])
    avg_sentiment = _avg([r.sentiment_score for r in responses])

    skills = session.student.profile.skills_list() if hasattr(session.student, "profile") else []
    company_tech = session.company.tech_stack_list()
    skill_match_pct = _skill_match(skills, company_tech)

    fit_score = predict_fit(
        skill_match_pct=skill_match_pct,
        avg_response_time=avg_response_time,
        avg_sentiment=avg_sentiment,
        confidence_score=confidence_score,
    )

    weak_areas = []
    if technical_score < 60:
        weak_areas.append("Technical depth")
    if hr_score < 60:
        weak_areas.append("Communication / HR readiness")
    if avg_response_time > 45:
        weak_areas.append("Response speed / confidence under pressure")
    if not weak_areas:
        weak_areas.append("None — well balanced")

    score, _ = SessionScore.objects.update_or_create(
        session=session,
        defaults=dict(
            technical_score=technical_score,
            hr_score=hr_score,
            confidence_score=confidence_score,
            fit_score=fit_score,
            weak_areas=", ".join(weak_areas),
        ),
    )
    return score


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else 0.0


def _skill_match(student_skills, company_tech):
    if not company_tech:
        return 50.0
    student_skills_lower = {s.lower() for s in student_skills}
    company_tech_lower = {t.lower() for t in company_tech}
    overlap = student_skills_lower & company_tech_lower
    return round(len(overlap) / len(company_tech_lower) * 100, 1)
