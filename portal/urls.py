from django.conf import settings
from django.contrib.auth import views as auth
from django.urls import path

from portal.accounts import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("settings/", views.business_settings, name="business_settings"),
    path("modules/", views.modules, name="modules"),
    path("modules/<int:module_id>/remove/", views.remove_module, name="remove_module"),
    path("calls/", views.calls, name="calls"),
    path("totals/", views.totals, name="totals"),
    path("test-call/", views.test_call, name="test_call"),
    path("call/<str:slug>/", views.call_link, name="call_link"),
    path("call-button.js", views.call_button_js, name="call_button_js"),
    path(
        "api/settings/<int:business_id>/",
        views.settings_for_core,
        name="settings_for_core",
    ),
    path("api/calls/", views.record_call, name="record_call"),
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
