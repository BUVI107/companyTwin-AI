from django.core.management.base import BaseCommand
from core.models import Company, Persona

COMPANIES = [
    dict(
        name="TCS Digital",
        logo_initial="TC",
        tech_stack="Java, Spring Boot, SQL, AWS",
        industry="IT Services",
        interview_style_tags="DSA-heavy, aptitude-first, formal",
        difficulty_level="medium",
        rounds_config="1. Aptitude test\n2. Technical interview (DSA + core CS)\n3. HR interview",
        tone_description="Formal, structured, follows a checklist of standard CS fundamentals questions.",
    ),
    dict(
        name="Zoho",
        logo_initial="ZH",
        tech_stack="Java, JavaScript, MySQL, React",
        industry="Product / SaaS",
        interview_style_tags="problem-solving, product-thinking, informal",
        difficulty_level="hard",
        rounds_config="1. Coding round\n2. Technical deep-dive\n3. Founder-style HR chat",
        tone_description="Informal and curious, digs deep into 'why' behind your design choices rather than rote answers.",
    ),
    dict(
        name="Infosys",
        logo_initial="IN",
        tech_stack="Java, Python, SQL",
        industry="IT Services",
        interview_style_tags="fundamentals-focused, communication-heavy",
        difficulty_level="easy",
        rounds_config="1. Technical MCQ\n2. Technical interview\n3. HR interview",
        tone_description="Polite and encouraging, focuses on communication skills as much as technical accuracy.",
    ),
    dict(
        name="Product Startup (Series A)",
        logo_initial="ST",
        tech_stack="Python, Django, React, PostgreSQL, Docker",
        industry="Startup",
        interview_style_tags="case-study-based, fast-paced, ownership-focused",
        difficulty_level="hard",
        rounds_config="1. Live coding / pairing round\n2. System design lite\n3. Culture/ownership chat with founder",
        tone_description="Fast-paced, informal, pushes hard on ownership and how you handle ambiguity.",
    ),
    dict(
        name="Wipro",
        logo_initial="WP",
        tech_stack="Java, SQL, Cloud Fundamentals",
        industry="IT Services",
        interview_style_tags="core-CS, aptitude, formal",
        difficulty_level="easy",
        rounds_config="1. Aptitude\n2. Technical interview\n3. HR interview",
        tone_description="Straightforward and formal, sticks closely to resume content and core CS basics.",
    ),
    dict(
        name="Cognizant",
        logo_initial="CG",
        tech_stack="Java, .NET, SQL, Cloud",
        industry="IT Services",
        interview_style_tags="scenario-based, communication-heavy",
        difficulty_level="medium",
        rounds_config="1. Technical interview\n2. Versant/communication round\n3. HR interview",
        tone_description="Friendly but scenario-driven — likes 'what would you do if...' questions.",
    ),
]

PERSONA_TEMPLATES = {
    "technical": (
        "You are the Technical Interviewer on a hiring panel for {company}. "
        "The company's real tech stack is: {tech_stack}. "
        "Its known interview style is: {tags}. Overall tone: {tone}. "
        "Ask one focused technical question at a time, grounded in the company's actual "
        "tech stack, and ask a natural follow-up based on the candidate's previous answer. "
        "Keep questions concise (1-3 sentences)."
    ),
    "hr": (
        "You are the HR Interviewer on a hiring panel for {company}. "
        "Known interview style: {tags}. Overall tone: {tone}. "
        "Ask one behavioral or culture-fit question at a time that matches this company's "
        "known tone. Keep it concise and conversational."
    ),
    "manager": (
        "You are the Panel Manager on a hiring panel for {company}, occasionally stepping in "
        "with pressure-testing or cross-functional questions. Tone: {tone}. Tags: {tags}. "
        "Ask one sharp, scenario-based question that tests judgement, not just knowledge."
    ),
}


class Command(BaseCommand):
    help = "Seed demo companies and their AI panel personas."

    def handle(self, *args, **options):
        created = 0
        for data in COMPANIES:
            company, was_created = Company.objects.update_or_create(
                name=data["name"], defaults=data
            )
            for ptype, template in PERSONA_TEMPLATES.items():
                Persona.objects.update_or_create(
                    company=company,
                    persona_type=ptype,
                    defaults=dict(
                        display_name=f"{company.name} {ptype.title()}",
                        system_prompt_template=template,
                    ),
                )
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} companies with personas."))
