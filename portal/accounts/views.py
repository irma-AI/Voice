# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import hmac
from typing import Any

from django import forms
from django.conf import settings
from django.contrib.auth import views as auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from portal.accounts import modules as module_rules
from portal.accounts import probe
from portal.accounts.models import LANGUAGES, Account, Business, Module, clean_email
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


class ModuleForm(forms.Form):
    """Adding a Module: a name and an address. The address is parsed once here into what the database stores."""

    name = forms.CharField(max_length=module_rules.NAME_MAX)
    address = forms.CharField(max_length=module_rules.URL_MAX)

    def __init__(self, *args: Any, business: Business, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.business = business

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if self.business.modules.filter(name=name).exists():  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            raise forms.ValidationError("You already have a Module with that name.")
        return name

    def clean_address(self) -> tuple[str, str, list[str]]:
        try:
            return module_rules.parse_address(
                self.cleaned_data["address"], settings.ALLOW_LOCAL_MODULES
            )
        except ValueError as e:
            raise forms.ValidationError(str(e)) from None

    def save(self) -> Module:
        url, command, args = self.cleaned_data["address"]
        return Module.objects.create(
            business=self.business,
            name=self.cleaned_data["name"],
            url=url,
            command=command,
            args=args,
        )


@login_required
def modules(request: HttpRequest) -> HttpResponse:
    """The Business's Modules, the Actions each offers right now, and the form to add one."""
    business = get_object_or_404(Business, account=request.user)
    form = ModuleForm(request.POST or None, business=business)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except (
            IntegrityError
        ):  # the database's own limit (ten per Business) or a name taken a moment ago
            form.add_error(
                None,
                f"The Module was not added: a Business has at most {module_rules.MODULES_MAX} Modules, with different names.",
            )
        else:
            return redirect("modules")
    mine = list(business.modules.order_by("id"))  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    offers = probe.what_they_offer(
        [(m.url, m.command, m.args) for m in mine], settings.ALLOW_LOCAL_MODULES
    )
    return render(
        request,
        "accounts/modules.html",
        {
            "form": form,
            "rows": list(zip(mine, offers, strict=True)),
            "full": len(mine) >= module_rules.MODULES_MAX,
        },
    )


@login_required
@require_POST
def remove_module(request: HttpRequest, module_id: int) -> HttpResponse:
    """The one way a Module goes: only one of the logged-in Business's own."""
    get_object_or_404(Module, pk=module_id, business__account=request.user).delete()
    return redirect("modules")


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
