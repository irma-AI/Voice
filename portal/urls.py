from django.contrib.auth import views as auth
from django.urls import path

from portal.accounts import agent, views

urlpatterns = [
    path("mcp/", agent.endpoint, name="agent_endpoint"),
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("settings/", views.business_settings, name="business_settings"),
    path("modules/", views.modules, name="modules"),
    path("modules/<int:module_id>/remove/", views.remove_module, name="remove_module"),
    path("tokens/", views.access_tokens, name="access_tokens"),
    path(
        "tokens/<int:token_id>/revoke/",
        views.revoke_access_token,
        name="revoke_access_token",
    ),
    path("changes/", views.pending_changes, name="pending_changes"),
    path(
        "changes/<int:change_id>/approve/",
        views.decide_change,
        {"decision": "approved"},
        name="approve_change",
    ),
    path(
        "changes/<int:change_id>/reject/",
        views.decide_change,
        {"decision": "rejected"},
        name="reject_change",
    ),
    path("calls/", views.calls, name="calls"),
    path("totals/", views.totals, name="totals"),
    path("logs/", views.call_logs, name="call_logs"),
    path("logs/<str:call_id>/", views.call_log, name="call_log"),
    path("test-call/", views.test_call, name="test_call"),
    path("call/<str:slug>/", views.call_link, name="call_link"),
    path("logo/<str:key>/", views.logo, name="logo"),
    path("call-button.js", views.call_button_js, name="call_button_js"),
    path(
        "api/settings/<int:business_id>/",
        views.settings_for_core,
        name="settings_for_core",
    ),
    path("api/calls/", views.record_call, name="record_call"),
    path("api/call-logs/", views.record_call_log, name="record_call_log"),
    path("login/", views.Login.as_view(), name="login"),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        views.Reset.as_view(),
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
