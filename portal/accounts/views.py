# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import hashlib
import hmac
import json
import logging
import unicodedata
from collections import defaultdict
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.contrib.auth import views as auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from portal.accounts import modules as module_rules
from portal.accounts import probe
from portal.accounts.domain import parse_domain
from portal.accounts.models import (
    CALL_KINDS,
    LANGUAGES,
    Account,
    Business,
    CallRecord,
    Module,
    clean_email,
)
from portal.accounts.theme import (
    DEEP_SEA,
    LOGO_MAX_BYTES,
    LOGO_PROBLEM,
    LOGO_SIGNATURES,
    logo_type,
    parse_accent,
    size_problem,
)
from portal.accounts.ticket import mint

log = logging.getLogger(__name__)

LOGIN_TRIES = 10
LOGIN_WINDOW = 15 * 60


class LoginForm(AuthenticationForm):
    def clean_username(self) -> str:
        return clean_email(self.cleaned_data["username"])

    def clean(self):
        # shortcut: counts per email in this process's memory (the image runs one worker), so a restart resets it; move to the database before a second worker. Locks the owner out too for the window, which beats guessing.
        # Normalised the way Django's username field does before it authenticates, so a look-alike spelling of one address shares one count.
        typed = unicodedata.normalize("NFKC", str(self.data.get("username", "")))
        key = (
            "login-failures:" + hashlib.sha256(clean_email(typed).encode()).hexdigest()
        )
        if cache.get(key, 0) >= LOGIN_TRIES:
            raise ValidationError(
                "Too many failed attempts. Try again in 15 minutes.", code="locked"
            )
        try:
            cleaned = super().clean()
        except ValidationError:
            cache.add(key, 0, LOGIN_WINDOW)
            try:
                cache.incr(key)
            except (
                ValueError
            ):  # the key expired between add and incr: this attempt starts a new window
                cache.set(key, 1, LOGIN_WINDOW)
            raise
        if (
            self.user_cache
        ):  # a blank password skips authenticate() and must not clear the count
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


def sees_totals(account: Any) -> bool:
    """False when `SUPER_ADMIN_EMAIL` is unset: nobody is let in."""
    return (
        bool(settings.SUPER_ADMIN_EMAIL) and account.email == settings.SUPER_ADMIN_EMAIL
    )


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    business = Business.objects.filter(account=request.user).first()
    call_url = business and settings.PORTAL_URL.rstrip("/") + reverse(
        "call_link", args=[business.call_slug]
    )
    return render(
        request,
        "accounts/dashboard.html",
        {
            "business": business,
            "sees_totals": sees_totals(request.user),
            "call_url": call_url,
            # The Business pastes this into its own website; the text is what a caller reads on the button.
            "button_html": call_url
            and f'<a href="{call_url}" target="_blank" rel="noopener">Prata med vår AI-assistent</a>',
        },
    )


@login_required
def calls(request: HttpRequest) -> HttpResponse:
    """The logged-in Business's recent calls: start, length, kind. No cost, no call id."""
    business = Business.objects.filter(account=request.user).first()
    # shortcut: lists every record, no paging (Petter chose "All calls", DECISIONS.md); add paging before a Business has thousands.
    records = (
        CallRecord.objects.filter(business=business).order_by("-started_at")
        if business
        else []
    )
    rows = [
        (
            r.started_at,
            f"{r.length_seconds // 60}:{r.length_seconds % 60:02d}",
            CALL_KINDS[r.kind],
        )
        for r in records
    ]
    return render(
        request,
        "accounts/calls.html",
        {"rows": rows, "time_zone": settings.TIME_ZONE},
    )


@login_required
def totals(request: HttpRequest) -> HttpResponse:
    """Every Business's calls, minutes and dollars per month, test calls apart from Call link calls. Only the Account whose email is `SUPER_ADMIN_EMAIL` may open it."""
    if not sees_totals(request.user):
        return HttpResponseForbidden("This page is not open to your account.")
    month = TruncMonth("started_at", tzinfo=ZoneInfo(settings.TIME_ZONE))
    sums = (
        CallRecord.objects.annotate(month=month)
        .values("month", "business_id", "business__name", "kind")
        .annotate(
            calls=Count("id"),
            seconds=Sum("length_seconds"),
            dollars=Sum("cost_usd"),
            unpriced=Count("id", filter=Q(cost_usd__isnull=True)),
        )
    )
    by_row: dict[tuple[Any, int, str], dict[str, tuple[int, str, str, int]]] = (
        defaultdict(dict)
    )
    for s in sums:
        by_row[(s["month"], s["business_id"], s["business__name"])][s["kind"]] = (
            s["calls"],
            f"{s['seconds'] / 60:.1f}",
            f"{s['dollars'] or Decimal(0):.4f}",
            s["unpriced"],
        )
    empty = (0, "0.0", "0.0000", 0)
    rows = [
        (
            month.strftime("%Y-%m"),
            name,
            [kinds.get(kind, empty) for kind in CALL_KINDS],
        )
        for (month, _, name), kinds in sorted(
            by_row.items(), key=lambda r: (-r[0][0].timestamp(), r[0][2], r[0][1])
        )
    ]
    return render(
        request,
        "accounts/totals.html",
        {
            "rows": rows,
            "kinds": list(CALL_KINDS.values()),
            "time_zone": settings.TIME_ZONE,
        },
    )


class SettingsForm(forms.ModelForm):
    # The editable settings, one for one with contract/business-settings.schema.json. The AI notice is not among them.
    languages = forms.MultipleChoiceField(
        choices=list(LANGUAGES.items()), widget=forms.CheckboxSelectMultiple
    )

    # Portal-only: the contract the core reads does not carry it. What was typed is reduced once here to the domain the database stores.
    website_domain = forms.CharField(
        label="Your website",
        required=False,
        max_length=2000,  # room for a pasted address; what is stored is at most DOMAIN_MAX
        help_text="The address of your website, for example www.example.se. Only the main domain (example.se) is kept. Leave it empty for none.",
    )

    def clean_website_domain(self) -> str:
        try:
            return parse_domain(self.cleaned_data["website_domain"])
        except ValueError as e:
            raise forms.ValidationError(str(e)) from None

    # The Theme (theme.py), shown only to the Business's Callers. The contract carries it as `theme`.
    logo = forms.FileField(
        label="Logo",
        required=False,
        widget=forms.FileInput(attrs={"accept": ",".join(LOGO_SIGNATURES)}),
        help_text=f"PNG, WebP or JPEG, at most {LOGO_MAX_BYTES // 1024} KB. Your Callers see it on the call page.",
    )
    remove_logo = forms.BooleanField(label="Remove my logo", required=False)
    use_accent = forms.BooleanField(label="Use an accent colour", required=False)
    accent = forms.CharField(
        label="Accent colour",
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={"type": "color"}),
        help_text="Your Callers see it on the call page and the Call button. Voice adjusts it when text on it would be hard to read.",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.initial["use_accent"] = bool(self.instance.accent)
        self.initial["accent"] = self.instance.accent or DEEP_SEA

    def clean_logo(self) -> bytes | None:
        """The upload's bytes, or None when nothing was uploaded. Its type is read from the bytes, never the file name."""
        upload = self.cleaned_data.get("logo")
        if not upload:
            return None
        if upload.size > LOGO_MAX_BYTES:
            raise forms.ValidationError(size_problem(upload.size))
        data = upload.read(LOGO_MAX_BYTES + 1)
        if len(data) > LOGO_MAX_BYTES:
            raise forms.ValidationError(size_problem(len(data)))
        if logo_type(data) is None:
            raise forms.ValidationError(LOGO_PROBLEM)
        return data

    def clean_accent(self) -> str:
        """The colour to store: "" when the box is unticked, so the colour input's own value is never saved by accident."""
        if not self.data.get("use_accent"):
            return ""
        try:
            return parse_accent(self.cleaned_data["accent"])
        except ValueError as e:
            raise forms.ValidationError(str(e)) from None

    def save(self, commit: bool = True) -> Business:
        business: Business = super().save(commit=False)
        if self.cleaned_data["logo"] is not None:
            business.set_logo(self.cleaned_data["logo"])
        elif self.cleaned_data["remove_logo"]:
            business.set_logo(None)
        business.accent = self.cleaned_data["accent"]
        if commit:
            business.save()
        return business

    class Meta:
        model = Business
        fields = ("name", "facts", "languages", "website_domain")
        widgets = {  # noqa: RUF012 (Django reads Meta as plain attributes)
            "facts": forms.Textarea(attrs={"rows": 12})
        }
        help_texts = {  # noqa: RUF012
            "facts": "Everything the agent should know about your business, in your own words: what you do, where, when you are open, what things cost."
        }


@login_required
def business_settings(request: HttpRequest) -> HttpResponse:
    business = get_object_or_404(Business, account=request.user)
    form = SettingsForm(request.POST or None, request.FILES or None, instance=business)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(f"{reverse('business_settings')}?saved=1")
    # A refused form leaves the Theme as saved: only save() writes the logo and the accent onto the instance.
    return render(
        request,
        "accounts/settings.html",
        {
            "form": form,
            "saved": "saved" in request.GET,
            "theme": business.theme(),
            "picked_accent": business.accent,
        },
    )


@require_GET
def logo(request: HttpRequest, key: str) -> HttpResponse:
    """A Business's logo, public on purpose: the core's call page loads it from here. The address is the hash of the bytes, so it names no Business."""
    business = Business.objects.filter(logo_key=key).exclude(logo=None).first()
    if business is None:
        raise Http404
    data = bytes(business.logo or b"")
    response = HttpResponse(data, content_type=logo_type(data))
    # The same address always holds the same bytes, so a browser may keep it for a year.
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'"
    response["Cross-Origin-Resource-Policy"] = "cross-origin"
    return response


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
    checking = request.method == "POST" and "check" in request.POST
    form = ModuleForm(None if checking else request.POST or None, business=business)
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
    # The Modules are asked only when the Business presses Check: a slow one would otherwise hold a request thread on every page view, and
    # those threads also answer the core's settings request at each call start.
    offers = (
        probe.what_they_offer(
            [(m.url, m.command, m.args) for m in mine], settings.ALLOW_LOCAL_MODULES
        )
        if checking
        else [None] * len(mine)
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


# What a Caller reads when the Business has not saved its website (English; Petter approved the words on 2026-10-17, VOI-71).
CALL_LINK_REFUSAL = (
    "This call can't be opened from here. Start it from the company's own website."
)


def to_core(business: Business, kind: str, domain: str = "") -> HttpResponse:
    """Sends a browser to the core's call page with a ticket for this one Business, the kind of call and the website allowed to frame the page: the only way a browser is let to call."""
    # Empty only on a local run; a ticket signed with nothing would be refused by the core anyway.
    if not settings.CORE_SECRET:
        return HttpResponse("Calls are not set up: CORE_SECRET is empty.", status=503)
    ticket = mint(settings.CORE_SECRET, business.pk, kind, domain)
    return redirect(f"{settings.CORE_URL.rstrip('/')}/?ticket={ticket}")


@login_required
@require_POST
def test_call(request: HttpRequest) -> HttpResponse:
    """A logged-in Business's own test call; it takes no Business from the request."""
    return to_core(get_object_or_404(Business, account=request.user), "test")


@require_GET
@never_cache
def call_link(request: HttpRequest, slug: str) -> HttpResponse:
    """A Business's public call link. Open to anyone, so anyone can start a call for that Business (there is no limit yet, DECISIONS.md), but only once it has saved its website (VOI-71): the core lets only that site frame the page."""
    business = get_object_or_404(Business, call_slug=slug)
    if not business.website_domain:
        log.warning("call link refused: Business %s has no website domain", business.pk)
        return HttpResponseForbidden(CALL_LINK_REFUSAL)
    return to_core(business, "call_link", business.website_domain)


def core_secret_sent(request: HttpRequest) -> bool:
    """Whether the request carries the shared secret as a Bearer token. An unset secret refuses everyone."""
    secret: str = settings.CORE_SECRET
    scheme, _, sent = request.headers.get("Authorization", "").partition(" ")
    return bool(
        secret
        and scheme == "Bearer"
        and hmac.compare_digest(sent.encode(), secret.encode())
    )


@require_GET
@never_cache
def settings_for_core(request: HttpRequest, business_id: int) -> HttpResponse:
    """The one address the core asks for a Business's settings. Behind the shared secret, not a login."""
    if not core_secret_sent(request):
        return JsonResponse({"error": "missing or wrong secret"}, status=401)
    business = get_object_or_404(Business, pk=business_id)
    return JsonResponse(business.as_settings())


class CallRecordForm(forms.ModelForm):  # pyright: ignore[reportMissingTypeArgument]
    """A Call record as the core sends it (contract/call-record.schema.json). The strict spellings are here because the form's defaults accept more than the contract does."""

    started_at = forms.RegexField(
        regex=r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,6})?Z$"
    )  # UTC only
    price_date = forms.DateField(input_formats=["%Y-%m-%d"], required=False)

    class Meta:
        model = CallRecord
        fields = "__all__"

    def clean_started_at(self) -> Any:
        try:
            return parse_datetime(self.cleaned_data["started_at"])
        except ValueError:
            raise ValidationError("not a real moment") from None

    def validate_unique(self) -> None:
        """A repeated call id is the core retrying, not a mistake: record_call answers it with the stored row."""


@csrf_exempt  # the shared secret gates it, not a session
@require_POST
@never_cache
def record_call(request: HttpRequest) -> HttpResponse:
    """The one address the core sends a finished call's record to. Stores it once per call id; the database refuses every later change."""
    if not core_secret_sent(request):
        return JsonResponse({"error": "missing or wrong secret"}, status=401)
    try:
        body = json.loads(request.body)
    except ValueError:
        body = None
    if not isinstance(body, dict) or body.keys() != CallRecordForm.base_fields.keys():  # pyright: ignore[reportUnknownMemberType]
        return JsonResponse({"error": "not a Call record"}, status=400)
    form = CallRecordForm(body)
    if not form.is_valid():
        # Field names only: a refused value never goes back out.
        return JsonResponse(
            {"error": "malformed Call record", "fields": sorted(form.errors)},
            status=400,
        )
    values = dict(form.cleaned_data)
    _, created = CallRecord.objects.get_or_create(
        call_id=values.pop("call_id"), defaults=values
    )
    return JsonResponse({"stored": True}, status=201 if created else 200)
