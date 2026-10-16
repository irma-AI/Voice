# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import hmac

from django import forms
from django.conf import settings
from django.contrib.auth import views as auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from portal.accounts.models import LANGUAGES, Account, Business, clean_email
from portal.accounts.ticket import mint

LOGIN_TRIES = 10
LOGIN_WINDOW = 15 * 60


class LoginForm(AuthenticationForm):
    def clean_username(self) -> str:
        return clean_email(self.cleaned_data["username"])

    def clean(self):
        # shortcut: counts per email in this process's memory (the image runs one worker), so a restart resets it; move to the database before a second worker. Locks the owner out too for the window, which beats guessing.
        key = f"login-failures:{clean_email(self.data.get('username', ''))}"
        if cache.get(key, 0) >= LOGIN_TRIES:
            raise ValidationError(
                "Too many failed attempts. Try again in 15 minutes.", code="locked"
            )
        try:
            cleaned = super().clean()
        except ValidationError:
            cache.add(key, 0, LOGIN_WINDOW)
            cache.incr(key)
            raise
        cache.delete(key)
        return cleaned


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
    return render(
        request,
        "accounts/dashboard.html",
        {"business": Business.objects.filter(account=request.user).first()},
    )


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


@login_required
@require_POST
def test_call(request: HttpRequest) -> HttpResponse:
    """The one way a browser gets to call for a Business: a ticket for the logged-in Business, and nothing else it could name."""
    business = get_object_or_404(Business, account=request.user)
    # Empty only on a local run; a ticket signed with nothing would be refused by the core anyway.
    if not settings.CORE_SECRET:
        return HttpResponse(
            "Test calls are not set up: CORE_SECRET is empty.", status=503
        )
    ticket = mint(settings.CORE_SECRET, business.pk)
    return redirect(f"{settings.CORE_URL.rstrip('/')}/?ticket={ticket}")


@require_GET
@never_cache
def settings_for_core(request: HttpRequest, business_id: int) -> HttpResponse:
    """The one address the core asks for a Business's settings. Behind the shared secret, not a login; an unset secret refuses everyone."""
    secret: str = settings.CORE_SECRET
    scheme, _, sent = request.headers.get("Authorization", "").partition(" ")
    if (
        not secret
        or scheme != "Bearer"
        or not hmac.compare_digest(sent.encode(), secret.encode())
    ):
        return JsonResponse({"error": "missing or wrong secret"}, status=401)
    business = get_object_or_404(Business, pk=business_id)
    return JsonResponse(business.as_settings())
