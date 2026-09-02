"""
Multi-persona AI interview engine.

Builds a company-specific "digital twin" panel out of 3 personas
(Technical / HR / Panel Manager) and orchestrates who speaks next.

Uses the OpenAI API when OPENAI_API_KEY is set in the environment.
Falls back to a deterministic offline question bank so the project
is fully demoable without any API key or internet access — this
fallback is what you'll use during your viva if Wi-Fi is unreliable.
"""
import os
import random

try:
    from openai import OpenAI
    _client = OpenAI() if os.environ.get("OPENAI_API_KEY") else None
except Exception:
    _client = None


# ---------------------------------------------------------------------
# Offline fallback question bank, keyed by persona type + difficulty.
# Used automatically when no API key is configured.
# ---------------------------------------------------------------------
FALLBACK_QUESTIONS = {
    "technical": {
        "easy": [
            "Walk me through a project on your resume — what was your specific contribution?",
            "What's the difference between a list and a tuple, and when would you use each?",
            "Explain how you'd debug an application that's running slower than expected.",
        ],
        "medium": [
            "Design a database schema for the system you just described. What are the key tables?",
            "How would you scale this application if traffic increased 10x overnight?",
            "Explain a time you had to optimize a slow piece of code. What did you change?",
        ],
        "hard": [
            "How would you design a rate limiter for a public API from scratch?",
            "Walk through the tradeoffs between SQL and NoSQL for this use case.",
            "Given the tech stack you listed, what's a failure mode you'd worry about in production?",
        ],
    },
    "hr": {
        "easy": [
            "Tell me about yourself and why you're interested in this role.",
            "What are you most proud of from your academic projects?",
            "How do you handle disagreements within a team?",
        ],
        "medium": [
            "Tell me about a time a project didn't go as planned. What did you do?",
            "Where do you see yourself in three years, and how does this role fit that?",
            "How do you prioritize when you have multiple deadlines at once?",
        ],
        "hard": [
            "Tell me about a time you had to push back on a decision you disagreed with.",
            "Describe a situation where you had to learn something completely new under time pressure.",
            "Why should we choose you over another candidate with a similar background?",
        ],
    },
    "manager": {
        "easy": [
            "If your teammate wasn't pulling their weight on a project, what would you do?",
            "What does good communication look like on a team, to you?",
        ],
        "medium": [
            "You're given a task with unclear requirements. Walk me through your first steps.",
            "How would you explain a technical decision to a non-technical stakeholder?",
        ],
        "hard": [
            "Two of your ideas conflict with your manager's approach — how do you handle that conversation?",
            "You discover a bug in production right before a big client demo. What do you do?",
        ],
    },
}

PERSONA_ORDER = ["technical", "hr", "manager", "technical", "hr", "manager"]


def build_system_prompt(company, persona_type):
    """Fill a persona's prompt template with the company's digital-twin profile."""
    persona = company.personas.filter(persona_type=persona_type).first()
    template = persona.system_prompt_template if persona else (
        "You are a {persona_type} interviewer at {company}. "
        "Tech stack: {tech_stack}. Interview style: {tags}. Tone: {tone}. "
        "Ask one focused question at a time and follow up based on the candidate's answer."
    )
    return template.format(
        company=company.name,
        tech_stack=", ".join(company.tech_stack_list()),
        tags=", ".join(company.tags_list()),
        tone=company.tone_description,
        persona_type=persona_type,
    )


def next_persona(session):
    """Decide which persona speaks next based on how many questions have been asked."""
    idx = session.question_count % len(PERSONA_ORDER)
    return PERSONA_ORDER[idx]


def generate_question(company, persona_type, conversation_history):
    """
    Returns the next interview question as a string.
    conversation_history: list of {"role": "assistant"/"user", "content": str}
    """
    if _client is not None:
        system_prompt = build_system_prompt(company, persona_type)
        messages = [{"role": "system", "content": system_prompt}] + conversation_history
        try:
            resp = _client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=200,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            pass  # fall through to offline bank on any API error

    # Offline fallback
    bank = FALLBACK_QUESTIONS[persona_type][company.difficulty_level]
    asked_count = sum(1 for m in conversation_history if m["role"] == "assistant")
    return bank[asked_count % len(bank)]
