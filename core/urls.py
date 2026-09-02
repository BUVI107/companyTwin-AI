from django.urls import path
from . import views

urlpatterns = [
    path("", views.company_select, name="company_select"),
    path("signup/", views.signup, name="signup"),
    path("profile/", views.profile_setup, name="profile_setup"),
    path("company/<int:company_id>/start/", views.start_session, name="start_session"),
    path("interview/<uuid:session_id>/", views.interview_room, name="interview_room"),
    path("results/<uuid:session_id>/", views.results, name="results"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
