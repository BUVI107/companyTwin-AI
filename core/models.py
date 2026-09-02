import uuid
from django.db import models
from django.contrib.auth.models import User


class Company(models.Model):
    """A curated profile of a target company used to build its AI 'digital twin'."""
    name = models.CharField(max_length=120, unique=True)
    logo_initial = models.CharField(max_length=4, default="CO")
    tech_stack = models.CharField(max_length=300, help_text="Comma separated, e.g. Java, Spring Boot, AWS")
    industry = models.CharField(max_length=120, default="IT Services")
    interview_style_tags = models.CharField(
        max_length=300,
        help_text="Comma separated tags e.g. DSA-heavy, culture-fit-heavy, case-study-based"
    )
    rounds_config = models.TextField(
        help_text="Describe the rounds this company typically runs, one per line."
    )
    tone_description = models.TextField(
        help_text="How this company's interviewers typically speak/behave, used in AI system prompts."
    )
    difficulty_level = models.CharField(
        max_length=20,
        choices=[("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")],
        default="medium",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def tech_stack_list(self):
        return [t.strip() for t in self.tech_stack.split(",") if t.strip()]

    def tags_list(self):
        return [t.strip() for t in self.interview_style_tags.split(",") if t.strip()]


class Persona(models.Model):
    """One AI panel member for a given company (Technical / HR / Panel Manager)."""
    PERSONA_TYPES = [
        ("technical", "Technical Interviewer"),
        ("hr", "HR Interviewer"),
        ("manager", "Panel Manager"),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="personas")
    persona_type = models.CharField(max_length=20, choices=PERSONA_TYPES)
    display_name = models.CharField(max_length=80)
    system_prompt_template = models.TextField(
        help_text="Prompt template. Use {company}, {tech_stack}, {tone}, {tags} as placeholders."
    )

    def __str__(self):
        return f"{self.company.name} — {self.get_persona_type_display()}"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    skills = models.CharField(max_length=400, blank=True, help_text="Comma separated skills")
    target_role = models.CharField(max_length=120, blank=True, default="Software Developer")

    def __str__(self):
        return self.user.username

    def skills_list(self):
        return [s.strip() for s in self.skills.split(",") if s.strip()]


class InterviewSession(models.Model):
    STATUS_CHOICES = [
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="sessions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_progress")
    current_persona = models.CharField(max_length=20, default="technical")
    question_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student.username} @ {self.company.name} ({self.status})"


class Response(models.Model):
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name="responses")
    persona_type = models.CharField(max_length=20)
    question = models.TextField()
    answer = models.TextField(blank=True)
    response_time_seconds = models.FloatField(default=0)
    sentiment_score = models.FloatField(default=0)   # -1 to 1
    confidence_score = models.FloatField(default=0)  # 0 to 100, derived
    asked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Q: {self.question[:40]}"


class SessionScore(models.Model):
    session = models.OneToOneField(InterviewSession, on_delete=models.CASCADE, related_name="score")
    technical_score = models.FloatField(default=0)
    hr_score = models.FloatField(default=0)
    confidence_score = models.FloatField(default=0)
    fit_score = models.FloatField(default=0)   # ML-predicted 0-100
    weak_areas = models.CharField(max_length=300, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Score for {self.session}"
