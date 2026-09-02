# CompanyTwin AI — Digital Twin Interview Simulator

Final-year project: an AI-powered platform that simulates a company-specific
"digital twin" interview panel (Technical / HR / Panel Manager personas),
scores behavioral confidence per answer using NLP, and predicts a Company Fit
Score using a trained ML model.

## Key features
- **Multi-persona AI interview engine** — 3 rotating personas per company,
  each with a distinct system prompt built from that company's real tech
  stack, tone, and interview-style tags. Live API mode (OpenAI) or a fully
  offline fallback question bank — the app is 100% demoable with zero
  internet access.
- **NLP scoring** — TextBlob sentiment analysis + a length/timing/sentiment
  confidence heuristic applied to every answer.
- **ML Fit Predictor** — a `RandomForestRegressor` trained on skill-match %,
  response time, sentiment, and confidence, predicting a 0–100 Company Fit
  Score.
- **Readiness dashboard** — a Chart.js radar chart comparing scores across
  every company practiced.
- **51 automated tests** covering auth, profile, the full interview
  workflow, AI engine (mocked), NLP scoring, ML prediction, models,
  dashboard/results, and cross-user security.

## Technology stack
| Layer | Tech |
|---|---|
| Backend | Django 6.1 |
| AI | OpenAI API (optional) + offline fallback engine |
| NLP | TextBlob |
| ML | scikit-learn (RandomForestRegressor), joblib |
| Database | SQLite (local) / PostgreSQL (production, via `DATABASE_URL`) |
| Frontend | Django templates, vanilla CSS (custom design system), Chart.js |
| Prod server | Gunicorn |

## System architecture
```
Browser → Django views → AI Engine (persona system prompts)
                        → Scoring (TextBlob sentiment/confidence)
                        → ML Fit Predictor (RandomForest, joblib-cached)
                        → SQLite/Postgres (Company, Persona, Session, Response, Score)
```
See `core/ai_engine.py`, `core/scoring.py`, and `core/ml/fit_predictor.py` for
the three core algorithmic components.

## Local development

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Optional: copy .env.example -> .env and edit if you want a real
# SECRET_KEY or an OpenAI API key. Defaults work out of the box.
cp .env.example .env

python manage.py migrate
python manage.py seed_companies      # populates 6 demo companies + personas
python manage.py createsuperuser     # optional, for /admin/
python manage.py runserver
```

Open **http://127.0.0.1:8000/**.

- `/signup/` — create a student account
- `/profile/` — enter skills (used for the Fit Score)
- `/` — pick a company, run the 6-question panel interview
- `/results/<id>/` — per-session scores + transcript
- `/dashboard/` — radar chart comparing all completed sessions
- `/admin/` — manage companies/personas (needs a superuser)

## Environment variables
See `.env.example` for the full list with descriptions. Summary:

| Variable | Purpose | Local default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django cryptographic key | insecure dev key (auto) |
| `DJANGO_DEBUG` | Debug mode | `True` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins (prod) | empty |
| `DJANGO_SECURE_SSL_REDIRECT` | Force HTTPS redirect | `True` (only applied when `DEBUG=False`) |
| `OPENAI_API_KEY` | Enables live AI-generated questions | unset → offline fallback |
| `DATABASE_URL` | Postgres connection string | unset → SQLite |

No secrets are hard-coded anywhere in the source. `.env` is git-ignored.

## Running tests

```bash
python manage.py test core
```

**51 tests, all passing** (verified — see below). Covers:
- Authentication (signup, login, logout, protected routes)
- Profile creation/update, empty-field handling
- Full interview workflow (persona rotation, 6-question completion, session
  state transitions)
- AI engine — offline fallback, mocked live-API success, mocked API-failure
  fallback, deterministic persona rotation (no test depends on a real
  external API call)
- NLP scoring — positive/negative/neutral sentiment, empty input, score
  bounds
- ML fit predictor — model loads, predictions stay in range, model is
  cached rather than retrained per call
- Model integrity — relationships, uniqueness constraints, cascade deletes
- Dashboard/results — correct data scoped to the logged-in user
- Security — cross-user access blocked (404, not leaked), anonymous users
  redirected, CSRF enforced on answer submission

## Deployment

This project is deployment-ready for Render (or any platform that supports
a `Procfile` + environment variables, e.g. Railway).

**Files provided:**
- `Procfile` — release (migrate + seed) and web (gunicorn) process types
- `render.yaml` — Render blueprint for one-click setup
- `.env.example` — required environment variables

**To deploy on Render:**
1. Push this repo to GitHub.
2. In Render, "New +" → "Blueprint" → point at the repo (uses `render.yaml`
   automatically), or create a Web Service manually with:
   - Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - Start command: `python manage.py migrate --noinput && python manage.py seed_companies && gunicorn companytwin.wsgi:application --bind 0.0.0.0:$PORT`
3. Set environment variables: `DJANGO_SECRET_KEY` (generate one), `DJANGO_DEBUG=False`,
   `DJANGO_ALLOWED_HOSTS=<your-app>.onrender.com`,
   `DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-app>.onrender.com`, and
   optionally `OPENAI_API_KEY`.
4. SQLite works fine for a demo deployment. For persistent multi-user data,
   add a Render PostgreSQL instance and set `DATABASE_URL` — the app
   detects it automatically and switches databases with no code change.

**Why SQLite is fine for a student demo, and when to switch:** Render's free
tier filesystem is ephemeral, so a SQLite file deployed there can reset on
redeploy — acceptable for a viva demo, not for a real multi-user product.
Swap in a managed Postgres add-on (one click on Render) and set
`DATABASE_URL` when you need durability.

> **Note on this delivery:** deployment itself (steps 1–4 above) needs to be
> run by you — the environment this project was built in has no network
> access to Render/Railway/etc. Everything needed to deploy in a single pass
> is included and has been verified locally (migrations, static files,
> production settings, `--deploy` checklist).

## Production configuration verified locally
- `python manage.py check` → 0 issues
- `python manage.py check --deploy` (with `DEBUG=False` + real-looking env vars) → 0 issues
- `python manage.py collectstatic --noinput` → succeeds, 131 files processed
  with `ManifestStaticFilesStorage` in production mode
- `python manage.py makemigrations --check` → no drift

## Project structure
```
companytwin/
├── core/
│   ├── models.py            → Company, Persona, StudentProfile, InterviewSession, Response, SessionScore
│   ├── views.py              → signup, profile, interview loop, results, dashboard
│   ├── ai_engine.py           → multi-persona question generation (API + offline fallback)
│   ├── scoring.py             → per-answer sentiment/confidence scoring
│   ├── tests.py                → 51 automated tests
│   ├── ml/
│   │   └── fit_predictor.py    → trains + serves the Company Fit ML model
│   ├── management/commands/
│   │   └── seed_companies.py   → populates demo company + persona data
│   └── admin.py
├── templates/                  → responsive, accessible HTML (semantic landmarks, labeled forms, focus states)
├── static/css/style.css         → design system (CSS variables, breakpoints at 320/375/390/414/768/1024/1440)
├── .env.example
├── .gitignore
├── Procfile
├── render.yaml
├── requirements.txt
└── manage.py
```

## Honest limitations (read before your viva)

- **The ML training data is synthetic.** `core/ml/fit_predictor.py` trains
  on a generated dataset built from an explainable rule + random noise,
  because no real historical interview-outcome dataset exists for this
  project. This is a standard, defensible approach for a final-year project
  with no access to real labeled data — but be ready to explain this clearly
  rather than imply the model learned from real outcomes. A real deployment
  would need a validated dataset of actual interview results before the fit
  score could be trusted as predictive.
- **Only 6 companies are seeded.** Easy to add more via `/admin/` or by
  extending `seed_companies.py`, but the current dataset is a demo set, not
  a comprehensive company database.
- **Deployment was prepared but not executed by me** — see the note in the
  Deployment section above. All configuration has been verified locally
  (checks, static files, migrations); the actual `git push` / Render setup
  is a ~10 minute manual step on your end.
- **UI is deliberately restrained**, not animated — per the brief, function
  and clarity were prioritized over visual flourish.
- **No email-based password reset** — `EMAIL_BACKEND` is configured
  correctly for future use, but no feature currently sends email.
