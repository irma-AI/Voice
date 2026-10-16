# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import hmac
import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from django import forms
from django.conf import settings
from django.contrib.auth import views as auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from portal.accounts.models import (
    LANGUAGES,
    LONGEST_CALL_SECONDS,
    Account,
    Business,
    Call,
    clean_email,
)
from portal.accounts.ticket import mint


class LoginForm(AuthenticationForm):
    def clean_username(self) -> str:
        return clean_email(self.cleaned_data["username"])


class ResetForm(PasswordResetForm):
    def get_users(self, email):
        # Django's form skips an account with no password yet, which would leave an invitee with an expired link stuck.
        return Account.objects.filter(email=clean_email(email), is_active=True)


class Login(auth.LoginView):
    authentication_form = LoginForm
    redirect_authenticated_user = True


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/home.html")


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    business = Business.objects.filter(account=request.user).first()
    context: dict[str, Any] = {"business": business}
    if business:
        calls, seconds = business.used_today()
        context |= {
            "calls_today": calls,
            "minutes_today": -(-seconds // 60),
            "call_url": settings.PORTAL_URL.rstrip("/")
            + reverse("call_link", args=[business.call_slug]),
        }
    return render(request, "accounts/dashboard.html", context)


class SettingsForm(forms.ModelForm):
    # The editable settings, one for one with contract/business-settings.schema.json. The AI notice is not among them.
    languages = forms.MultipleChoiceField(
        choices=list(LANGUAGES.items()), widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Business
        fields = ("name", "facts", "languages")
        widgets = {  # noqa: RUF012 (Django reads Meta as plain attributes)
            "facts": forms.Textarea(attrs={"rows": 12})
        }
        help_texts = {  # noqa: RUF012
            "facts": "Everything the agent should know about your business, in your own words: what you do, where, when you are open, what things cost."
        }


@login_required
def business_settings(request: HttpRequest) -> HttpResponse:
    business = get_object_or_404(Business, account=request.user)
    form = SettingsForm(request.POST or None, instance=business)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(f"{reverse('business_settings')}?saved=1")
    return render(
        request,
        "accounts/settings.html",
        {"form": form, "saved": "saved" in request.GET},
    )


def to_core(business: Business) -> HttpResponse:
    """Sends a browser to the core's call page with a ticket for this one Business: the only way a browser is let to call."""
    # Empty only on a local run; a ticket signed with nothing would be refused by the core anyway.
    if not settings.CORE_SECRET:
        return HttpResponse("Calls are not set up: CORE_SECRET is empty.", status=503)
    ticket = mint(settings.CORE_SECRET, business.pk)
    return redirect(f"{settings.CORE_URL.rstrip('/')}/?ticket={ticket}")


@login_required
@require_POST
def test_call(request: HttpRequest) -> HttpResponse:
    """A logged-in Business's own test call; it takes no Business from the request."""
    return to_core(get_object_or_404(Business, account=request.user))


@require_GET
@never_cache
def call_link(request: HttpRequest, slug: str) -> HttpResponse:
    """A Business's public call link. Open to anyone: the core's limits and off switch decide whether the call is let start."""
    return to_core(get_object_or_404(Business, call_slug=slug))


def core_only(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Behind the shared secret, not a session or a CSRF token: the core has neither. An unset secret refuses everyone."""

    @wraps(view)
    def checked(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        secret: str = settings.CORE_SECRET
        scheme, _, sent = request.headers.get("Authorization", "").partition(" ")
        if (
            not secret
            or scheme != "Bearer"
            or not hmac.compare_digest(sent.encode(), secret.encode())
        ):
            return JsonResponse({"error": "missing or wrong secret"}, status=401)
        return view(request, *args, **kwargs)

    return csrf_exempt(never_cache(checked))


@require_GET
@core_only
def settings_for_core(request: HttpRequest, business_id: int) -> HttpResponse:
    """The one address the core asks for a Business's settings."""
    business = get_object_or_404(Business, pk=business_id)
    return JsonResponse(business.as_settings())


@require_POST
@core_only
def start_call(request: HttpRequest, business_id: int) -> HttpResponse:
    """The one address that lets a call start: the core opens no model session without the `call` it answers with."""
    business = get_object_or_404(Business, pk=business_id)
    call = business.start_call()
    if isinstance(call, str):
        return JsonResponse({"refused": call}, status=403)
    return JsonResponse({"call": call.pk}, status=201)


@require_POST
@core_only
def end_call(request: HttpRequest, call_id: int) -> HttpResponse:
    """The core reports how long a call ran. Only the first report counts, and none is ever longer than a call can run."""
    call = get_object_or_404(Call, pk=call_id)
    try:
        seconds = int(json.loads(request.body)["seconds"])
    except (ValueError, KeyError, TypeError, OverflowError):
        return JsonResponse({"error": "seconds must be a whole number"}, status=400)
    if seconds < 0:
        return JsonResponse({"error": "seconds must not be negative"}, status=400)
    Call.objects.filter(pk=call.pk, seconds__isnull=True).update(
        seconds=min(seconds, LONGEST_CALL_SECONDS)
    )
    return JsonResponse({}, status=200)
