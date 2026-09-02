from django.contrib import admin
from .models import Company, Persona, StudentProfile, InterviewSession, Response, SessionScore


class PersonaInline(admin.TabularInline):
    model = Persona
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "difficulty_level", "created_at")
    search_fields = ("name",)
    inlines = [PersonaInline]


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ("company", "persona_type", "display_name")
    list_filter = ("persona_type",)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "target_role")


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ("student", "company", "status", "question_count", "started_at")
    list_filter = ("status", "company")


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("session", "persona_type", "response_time_seconds", "sentiment_score", "confidence_score")


@admin.register(SessionScore)
class SessionScoreAdmin(admin.ModelAdmin):
    list_display = ("session", "technical_score", "hr_score", "fit_score")
