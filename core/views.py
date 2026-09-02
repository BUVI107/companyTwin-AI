import time
import json
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import JsonResponse

from .models import Company, StudentProfile, InterviewSession, Response
from . import ai_engine
from .scoring import score_response, compute_session_score

QUESTIONS_PER_SESSION = 6


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            StudentProfile.objects.create(user=user)
            login(request, user)
            return redirect("company_select")
    else:
        form = UserCreationForm()
    return render(request, "registration/signup.html", {"form": form})


@login_required
def profile_setup(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        profile.skills = request.POST.get("skills", "")
        profile.target_role = request.POST.get("target_role", "Software Developer")
        profile.save()
        return redirect("company_select")
    return render(request, "core/profile_setup.html", {"profile": profile})


@login_required
def company_select(request):
    companies = Company.objects.all().order_by("name")
    past_sessions = request.user.sessions.filter(status="completed").select_related("company", "score")
    return render(request, "core/company_select.html", {
        "companies": companies,
        "past_sessions": past_sessions,
    })


@login_required
def start_session(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    session = InterviewSession.objects.create(student=request.user, company=company)
    return redirect("interview_room", session_id=session.id)


@login_required
def interview_room(request, session_id):
    session = get_object_or_404(InterviewSession, id=session_id, student=request.user)

    if session.status == "completed":
        return redirect("results", session_id=session.id)

    if request.method == "POST":
        answer = request.POST.get("answer", "").strip()
        question_id = request.POST.get("question_id")
        started_at = float(request.POST.get("started_at", time.time()))
        response_time = max(0.0, time.time() - started_at)

        resp = get_object_or_404(Response, id=question_id, session=session)
        sentiment, confidence = score_response(answer, response_time)
        resp.answer = answer
        resp.response_time_seconds = round(response_time, 1)
        resp.sentiment_score = sentiment
        resp.confidence_score = confidence
        resp.save()

        session.question_count += 1
        if session.question_count >= QUESTIONS_PER_SESSION:
            session.status = "completed"
            session.completed_at = timezone.now()
            session.save()
            compute_session_score(session)
            return redirect("results", session_id=session.id)
        session.save()

    # Build conversation history for the AI engine from past responses
    history = []
    for r in session.responses.all():
        history.append({"role": "assistant", "content": r.question})
        if r.answer:
            history.append({"role": "user", "content": r.answer})

    persona_type = ai_engine.next_persona(session)
    question_text = ai_engine.generate_question(session.company, persona_type, history)

    current_response = Response.objects.create(
        session=session,
        persona_type=persona_type,
        question=question_text,
    )
    session.current_persona = persona_type
    session.save()

    persona_labels = {"technical": "Technical Interviewer", "hr": "HR Interviewer", "manager": "Panel Manager"}

    return render(request, "core/interview_room.html", {
        "session": session,
        "company": session.company,
        "question": current_response,
        "persona_label": persona_labels.get(persona_type, persona_type),
        "progress": session.question_count,
        "total": QUESTIONS_PER_SESSION,
        "now_ts": time.time(),
    })


@login_required
def results(request, session_id):
    session = get_object_or_404(InterviewSession, id=session_id, student=request.user)
    score = getattr(session, "score", None)
    responses = session.responses.all()
    return render(request, "core/results.html", {
        "session": session,
        "score": score,
        "responses": responses,
    })


@login_required
def dashboard(request):
    sessions = request.user.sessions.filter(status="completed").select_related("company", "score")
    chart_data = {
        "labels": [s.company.name for s in sessions],
        "fit": [s.score.fit_score if hasattr(s, "score") else 0 for s in sessions],
        "technical": [s.score.technical_score if hasattr(s, "score") else 0 for s in sessions],
        "hr": [s.score.hr_score if hasattr(s, "score") else 0 for s in sessions],
    }
    return render(request, "core/dashboard.html", {
        "sessions": sessions,
        "chart_data_json": json.dumps(chart_data),
    })
