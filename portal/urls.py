from django.conf import settings
from django.contrib.auth import views as auth
from django.urls import path

from portal.accounts import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("login/", views.Login.as_view(), name="login"),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        auth.PasswordResetView.as_view(
            form_class=views.ResetForm,
            extra_email_context={"portal_url": settings.PORTAL_URL.rstrip("/")},
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        auth.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/done/",
        auth.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
