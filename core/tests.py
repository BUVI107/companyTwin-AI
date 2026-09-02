"""
Automated test suite for CompanyTwin AI.

Covers: authentication, profile, full interview workflow, AI engine
(with mocked external API + offline fallback), NLP scoring, ML fit
predictor, model integrity, dashboard/results, and cross-user access
security.

Run with:  python manage.py test
"""
import time
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from core.models import (
    Company, Persona, StudentProfile, InterviewSession, Response, SessionScore,
)
from core import ai_engine, scoring
from core.ml import fit_predictor


def make_company(name="TestCo"):
    company = Company.objects.create(
        name=name,
        tech_stack="Python, Django, SQL",
        industry="IT Services",
        interview_style_tags="DSA-heavy, formal",
        difficulty_level="medium",
        rounds_config="1. Technical\n2. HR",
        tone_description="Formal and structured.",
    )
    for ptype in ("technical", "hr", "manager"):
        Persona.objects.create(
            company=company,
            persona_type=ptype,
            display_name=f"{name} {ptype}",
            system_prompt_template="You are the {persona_type} interviewer at {company}. Stack: {tech_stack}.",
        )
    return company


class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = make_company()

    def test_signup_creates_user_and_profile(self):
        resp = self.client.post(reverse("signup"), {
            "username": "alice", "password1": "StrongPass123!", "password2": "StrongPass123!",
        })
        self.assertTrue(User.objects.filter(username="alice").exists())
        self.assertTrue(StudentProfile.objects.filter(user__username="alice").exists())
        self.assertEqual(resp.status_code, 302)

    def test_signup_rejects_mismatched_passwords(self):
        resp = self.client.post(reverse("signup"), {
            "username": "bob", "password1": "StrongPass123!", "password2": "DifferentPass456!",
        })
        self.assertFalse(User.objects.filter(username="bob").exists())
        self.assertEqual(resp.status_code, 200)

    def test_signup_rejects_duplicate_username(self):
        User.objects.create_user(username="carol", password="StrongPass123!")
        resp = self.client.post(reverse("signup"), {
            "username": "carol", "password1": "AnotherPass123!", "password2": "AnotherPass123!",
        })
        self.assertEqual(User.objects.filter(username="carol").count(), 1)
        self.assertEqual(resp.status_code, 200)

    def test_login_success(self):
        User.objects.create_user(username="dave", password="StrongPass123!")
        resp = self.client.post(reverse("login"), {"username": "dave", "password": "StrongPass123!"})
        self.assertEqual(resp.status_code, 302)

    def test_login_failure_wrong_password(self):
        User.objects.create_user(username="erin", password="StrongPass123!")
        resp = self.client.post(reverse("login"), {"username": "erin", "password": "WrongPassword"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    def test_logout(self):
        User.objects.create_user(username="frank", password="StrongPass123!")
        self.client.login(username="frank", password="StrongPass123!")
        resp = self.client.post(reverse("logout"))
        self.assertIn(resp.status_code, (200, 302))
        resp2 = self.client.get(reverse("dashboard"))
        self.assertEqual(resp2.status_code, 302)

    def test_protected_pages_require_login(self):
        for url_name, kwargs in [("dashboard", {}), ("profile_setup", {}), ("company_select", {})]:
            resp = self.client.get(reverse(url_name, kwargs=kwargs))
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/accounts/login/", resp.url)

    def test_unauthenticated_cannot_start_session(self):
        resp = self.client.get(reverse("start_session", args=[self.company.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(InterviewSession.objects.count(), 0)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="grace", password="StrongPass123!")
        StudentProfile.objects.create(user=self.user)
        self.client = Client()
        self.client.login(username="grace", password="StrongPass123!")

    def test_profile_update(self):
        resp = self.client.post(reverse("profile_setup"), {
            "skills": "Java, Python, Django", "target_role": "Backend Developer",
        })
        self.assertEqual(resp.status_code, 302)
        profile = StudentProfile.objects.get(user=self.user)
        self.assertEqual(profile.target_role, "Backend Developer")
        self.assertIn("Java", profile.skills_list())

    def test_profile_skills_list_parses_csv(self):
        profile = StudentProfile.objects.get(user=self.user)
        profile.skills = "Java,  Python ,SQL"
        profile.save()
        self.assertEqual(profile.skills_list(), ["Java", "Python", "SQL"])

    def test_profile_handles_empty_skills(self):
        resp = self.client.post(reverse("profile_setup"), {"skills": "", "target_role": "Developer"})
        self.assertEqual(resp.status_code, 302)
        profile = StudentProfile.objects.get(user=self.user)
        self.assertEqual(profile.skills_list(), [])


class InterviewWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="heidi", password="StrongPass123!")
        StudentProfile.objects.create(user=self.user, skills="Python, Django, SQL")
        self.company = make_company()
        self.client = Client()
        self.client.login(username="heidi", password="StrongPass123!")

    def test_company_select_lists_companies(self):
        resp = self.client.get(reverse("company_select"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.company.name)

    def test_start_session_creates_session(self):
        resp = self.client.get(reverse("start_session", args=[self.company.id]))
        self.assertEqual(resp.status_code, 302)
        session = InterviewSession.objects.get(student=self.user, company=self.company)
        self.assertEqual(session.status, "in_progress")
        self.assertEqual(session.question_count, 0)

    def test_persona_rotates_across_questions(self):
        self.client.get(reverse("start_session", args=[self.company.id]))
        session = InterviewSession.objects.get(student=self.user, company=self.company)
        seen_personas = []
        for _ in range(6):
            self.client.get(reverse("interview_room", args=[session.id]))
            session.refresh_from_db()
            latest = session.responses.order_by("-asked_at").first()
            seen_personas.append(latest.persona_type)
            self.client.post(reverse("interview_room", args=[session.id]), {
                "question_id": latest.id,
                "answer": "A reasonably detailed answer explaining my approach and reasoning.",
                "started_at": time.time() - 20,
            })
            session.refresh_from_db()
        self.assertEqual(set(seen_personas), {"technical", "hr", "manager"})

    def test_full_interview_completes_after_six_questions(self):
        self.client.get(reverse("start_session", args=[self.company.id]))
        session = InterviewSession.objects.get(student=self.user, company=self.company)
        resp = None
        for i in range(6):
            self.client.get(reverse("interview_room", args=[session.id]))
            session.refresh_from_db()
            q = session.responses.order_by("-asked_at").first()
            resp = self.client.post(reverse("interview_room", args=[session.id]), {
                "question_id": q.id,
                "answer": f"Detailed answer number {i + 1} with clear reasoning.",
                "started_at": time.time() - 15,
            }, follow=True)
        session.refresh_from_db()
        self.assertEqual(session.status, "completed")
        self.assertEqual(session.question_count, 6)
        self.assertIsNotNone(session.completed_at)
        self.assertTrue(SessionScore.objects.filter(session=session).exists())
        self.assertEqual(resp.request["PATH_INFO"], reverse("results", args=[session.id]))

    def test_answer_persists_response_time_and_scores(self):
        self.client.get(reverse("start_session", args=[self.company.id]))
        session = InterviewSession.objects.get(student=self.user, company=self.company)
        self.client.get(reverse("interview_room", args=[session.id]))
        q = session.responses.order_by("-asked_at").first()
        self.client.post(reverse("interview_room", args=[session.id]), {
            "question_id": q.id,
            "answer": "This is a thoughtful, fairly detailed answer to the question asked.",
            "started_at": time.time() - 22,
        })
        q.refresh_from_db()
        self.assertGreater(q.response_time_seconds, 0)
        self.assertNotEqual(q.answer, "")
        self.assertTrue(-1.0 <= q.sentiment_score <= 1.0)
        self.assertTrue(0.0 <= q.confidence_score <= 100.0)

    def test_cannot_reopen_completed_session_for_new_questions(self):
        self.client.get(reverse("start_session", args=[self.company.id]))
        session = InterviewSession.objects.get(student=self.user, company=self.company)
        for i in range(6):
            self.client.get(reverse("interview_room", args=[session.id]))
            session.refresh_from_db()
            q = session.responses.order_by("-asked_at").first()
            self.client.post(reverse("interview_room", args=[session.id]), {
                "question_id": q.id, "answer": f"Answer {i}", "started_at": time.time() - 10,
            })
        session.refresh_from_db()
        self.assertEqual(session.status, "completed")
        resp = self.client.get(reverse("interview_room", args=[session.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("results", args=[session.id]))


class AIEngineTests(TestCase):
    def setUp(self):
        self.company = make_company()

    def test_offline_fallback_used_when_no_client_configured(self):
        with patch.object(ai_engine, "_client", None):
            question = ai_engine.generate_question(self.company, "technical", [])
            self.assertIsInstance(question, str)
            self.assertGreater(len(question), 0)

    def test_offline_fallback_covers_all_persona_types(self):
        with patch.object(ai_engine, "_client", None):
            for ptype in ("technical", "hr", "manager"):
                q = ai_engine.generate_question(self.company, ptype, [])
                self.assertIsInstance(q, str)
                self.assertGreater(len(q), 0)

    def test_live_api_path_is_used_when_client_available(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Mocked question from live API."))]
        mock_client.chat.completions.create.return_value = mock_response

        with patch.object(ai_engine, "_client", mock_client):
            question = ai_engine.generate_question(self.company, "technical", [])
            self.assertEqual(question, "Mocked question from live API.")
            mock_client.chat.completions.create.assert_called_once()

    def test_falls_back_gracefully_on_api_failure(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API unreachable")

        with patch.object(ai_engine, "_client", mock_client):
            question = ai_engine.generate_question(self.company, "hr", [])
            self.assertIsInstance(question, str)
            self.assertGreater(len(question), 0)

    def test_persona_rotation_order_is_deterministic(self):
        session = InterviewSession.objects.create(
            student=User.objects.create_user(username="ivan", password="StrongPass123!"),
            company=self.company,
        )
        rotation = []
        for i in range(6):
            session.question_count = i
            rotation.append(ai_engine.next_persona(session))
        self.assertEqual(rotation, ["technical", "hr", "manager", "technical", "hr", "manager"])

    def test_build_system_prompt_includes_company_data(self):
        prompt = ai_engine.build_system_prompt(self.company, "technical")
        self.assertIn(self.company.name, prompt)
        self.assertIn("Python", prompt)


class ScoringTests(TestCase):
    def test_positive_answer_yields_positive_sentiment(self):
        sentiment, confidence = scoring.score_response(
            "This was an excellent and wonderful project, I loved every part of building it.", 25
        )
        self.assertGreater(sentiment, 0)

    def test_negative_answer_yields_negative_sentiment(self):
        sentiment, confidence = scoring.score_response(
            "This was a terrible and frustrating experience, everything went wrong.", 25
        )
        self.assertLess(sentiment, 0)

    def test_neutral_answer_near_zero_sentiment(self):
        sentiment, confidence = scoring.score_response(
            "The application uses Django for the backend and SQL for storage.", 25
        )
        self.assertTrue(-0.3 <= sentiment <= 0.3)

    def test_empty_answer_returns_zero_scores(self):
        sentiment, confidence = scoring.score_response("", 10)
        self.assertEqual(sentiment, 0.0)
        self.assertEqual(confidence, 0.0)

    def test_whitespace_only_answer_returns_zero_scores(self):
        sentiment, confidence = scoring.score_response("   \n\t  ", 10)
        self.assertEqual(sentiment, 0.0)
        self.assertEqual(confidence, 0.0)

    def test_confidence_score_within_bounds(self):
        for text, t in [
            ("Short.", 5),
            ("A " * 200, 30),
            ("Medium length answer with reasonable detail here.", 200),
        ]:
            _, confidence = scoring.score_response(text, t)
            self.assertGreaterEqual(confidence, 0.0)
            self.assertLessEqual(confidence, 100.0)

    def test_sentiment_score_within_bounds(self):
        sentiment, _ = scoring.score_response("Absolutely fantastic amazing incredible wonderful!", 20)
        self.assertGreaterEqual(sentiment, -1.0)
        self.assertLessEqual(sentiment, 1.0)


class FitPredictorTests(TestCase):
    def test_model_loads_without_error(self):
        model = fit_predictor._get_model()
        self.assertIsNotNone(model)

    def test_prediction_returns_float_in_range(self):
        score = fit_predictor.predict_fit(
            skill_match_pct=75, avg_response_time=25, avg_sentiment=0.3, confidence_score=70
        )
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)

    def test_prediction_extreme_inputs_stay_in_range(self):
        low = fit_predictor.predict_fit(0, 90, -1.0, 0)
        high = fit_predictor.predict_fit(100, 30, 1.0, 100)
        for score in (low, high):
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 100.0)
        self.assertGreaterEqual(high, low)

    def test_higher_skill_match_yields_higher_or_equal_fit(self):
        low_skill = fit_predictor.predict_fit(10, 30, 0.2, 60)
        high_skill = fit_predictor.predict_fit(90, 30, 0.2, 60)
        self.assertGreaterEqual(high_skill, low_skill)

    def test_model_does_not_retrain_on_every_prediction(self):
        fit_predictor._model = None
        m1 = fit_predictor._get_model()
        m2 = fit_predictor._get_model()
        self.assertIs(m1, m2)


class ModelTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.user = User.objects.create_user(username="judy", password="StrongPass123!")

    def test_company_str_and_helpers(self):
        self.assertEqual(str(self.company), "TestCo")
        self.assertIn("Python", self.company.tech_stack_list())
        self.assertIn("DSA-heavy", self.company.tags_list())

    def test_company_name_is_unique(self):
        with self.assertRaises(Exception):
            Company.objects.create(name="TestCo", tech_stack="X", interview_style_tags="Y",
                                    rounds_config="Z", tone_description="W")

    def test_persona_company_relationship(self):
        self.assertEqual(self.company.personas.count(), 3)
        types = set(self.company.personas.values_list("persona_type", flat=True))
        self.assertEqual(types, {"technical", "hr", "manager"})

    def test_interview_session_defaults(self):
        session = InterviewSession.objects.create(student=self.user, company=self.company)
        self.assertEqual(session.status, "in_progress")
        self.assertEqual(session.question_count, 0)
        self.assertIsNotNone(session.id)

    def test_response_belongs_to_session(self):
        session = InterviewSession.objects.create(student=self.user, company=self.company)
        r = Response.objects.create(session=session, persona_type="technical", question="Q?")
        self.assertEqual(session.responses.count(), 1)
        self.assertEqual(r.session, session)

    def test_session_score_one_to_one(self):
        session = InterviewSession.objects.create(student=self.user, company=self.company)
        SessionScore.objects.create(session=session, fit_score=80)
        self.assertEqual(session.score.fit_score, 80)
        with self.assertRaises(Exception):
            SessionScore.objects.create(session=session, fit_score=50)

    def test_deleting_session_cascades_responses(self):
        session = InterviewSession.objects.create(student=self.user, company=self.company)
        Response.objects.create(session=session, persona_type="technical", question="Q?")
        session_id = session.id
        session.delete()
        self.assertEqual(Response.objects.filter(session_id=session_id).count(), 0)


class DashboardResultsTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.user = User.objects.create_user(username="karl", password="StrongPass123!")
        StudentProfile.objects.create(user=self.user)
        self.client = Client()
        self.client.login(username="karl", password="StrongPass123!")

    def test_dashboard_empty_state(self):
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_shows_completed_sessions_only(self):
        session = InterviewSession.objects.create(student=self.user, company=self.company, status="completed")
        SessionScore.objects.create(session=session, fit_score=88)
        InterviewSession.objects.create(student=self.user, company=self.company)

        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["sessions"].count(), 1)
        self.assertContains(resp, self.company.name)

    def test_results_page_shows_correct_session_data(self):
        session = InterviewSession.objects.create(student=self.user, company=self.company, status="completed")
        SessionScore.objects.create(session=session, fit_score=72, technical_score=65, hr_score=80)
        resp = self.client.get(reverse("results", args=[session.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "72")


class SecurityTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.owner = User.objects.create_user(username="owner", password="StrongPass123!")
        self.intruder = User.objects.create_user(username="intruder", password="StrongPass123!")
        self.session = InterviewSession.objects.create(student=self.owner, company=self.company, status="completed")
        SessionScore.objects.create(session=self.session, fit_score=90)
        self.client = Client()

    def test_user_cannot_view_another_users_results(self):
        self.client.login(username="intruder", password="StrongPass123!")
        resp = self.client.get(reverse("results", args=[self.session.id]))
        self.assertEqual(resp.status_code, 404)

    def test_user_cannot_view_another_users_interview_room(self):
        self.client.login(username="intruder", password="StrongPass123!")
        resp = self.client.get(reverse("interview_room", args=[self.session.id]))
        self.assertEqual(resp.status_code, 404)

    def test_invalid_session_id_returns_404(self):
        self.client.login(username="owner", password="StrongPass123!")
        resp = self.client.get(reverse("results", args=["00000000-0000-0000-0000-000000000000"]))
        self.assertEqual(resp.status_code, 404)

    def test_anonymous_user_redirected_from_results(self):
        resp = self.client.get(reverse("results", args=[self.session.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_csrf_protection_enabled_on_answer_submission(self):
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.login(username="owner", password="StrongPass123!")
        q = Response.objects.create(session=self.session, persona_type="technical", question="Q?")
        resp = strict_client.post(reverse("interview_room", args=[self.session.id]), {
            "question_id": q.id, "answer": "test", "started_at": time.time(),
        })
        self.assertEqual(resp.status_code, 403)

    def test_dashboard_only_shows_own_sessions(self):
        self.client.login(username="intruder", password="StrongPass123!")
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.context["sessions"].count(), 0)
