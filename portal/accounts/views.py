# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import hashlib
import hmac
import json
import logging
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, time
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
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
from django.templatetags.static import static
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_GET, require_POST

from portal.accounts import modules as module_rules
from portal.accounts import probe, tokens
from portal.accounts.domain import parse_domain, shown_domain
from portal.accounts.models import (
    CALL_KINDS,
    LANGUAGES,
    AccessToken,
    Account,
    Business,
    CallRecord,
    Module,
    clean_email,
)
from portal.accounts.theme import (
    DEEP_SEA,
    FOAM,
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


def back_to(page: str) -> HttpResponse:
    """A GET of an address that only acts on a POST: it does nothing and goes back to the page with the button. It is where the login sends a Business whose session ended as it pressed that button."""
    return redirect(page)


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    """A form refused by the CSRF check, usually one left open while the session ended or another tab logged in or out."""
    log.warning("csrf refused: %s", reason)
    # Back to the form's page; logout's address has no page of its own.
    url_name = request.resolver_match and request.resolver_match.url_name
    again = reverse("home") if url_name == "logout" else request.path
    return render(request, "csrf_failure.html", {"again": again}, status=403)


class LoginForm(AuthenticationForm):
    error_messages = {  # noqa: RUF012 (Django reads it as a plain attribute)
        **AuthenticationForm.error_messages,
        # Django's own says both fields may be case-sensitive; the email is not.
        "invalid_login": "That email and password do not match. Check both and try again.",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        # The username is an email address: a phone shows the email keyboard and leaves the text as typed.
        widget = self.fields["username"].widget
        widget.input_type = (
            "email"  # not attrs["type"]: that would render a second type attribute
        )
        widget.attrs.update(
            inputmode="email", autocapitalize="none", spellcheck="false"
        )

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
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        self.fields["email"].widget.attrs.update(
            inputmode="email", autocapitalize="none", spellcheck="false"
        )

    def get_users(self, email):
        # Django's form skips an account with no password yet, which would leave an invitee with an expired link stuck.
        return Account.objects.filter(email=clean_email(email), is_active=True)


class Login(auth.LoginView):
    authentication_form = LoginForm
    redirect_authenticated_user = True


def home(request: HttpRequest) -> HttpResponse:
    """The landing page, open to everyone; a logged-in Business sees a link to its dashboard where a visitor sees Log in."""
    return render(
        request,
        "accounts/home.html",
        {"contact_email": settings.CONTACT_EMAIL, **showcase()},
    )


def showcase() -> dict[str, Any]:
    """The landing page's example Business, shown as a read-out like the Portal's Module row: made-up content, never saved."""
    agent = {
        "name": "Example Salon",
        "instructions": "We are a hair salon. Open Monday to Friday 09:00 to 17:00 and Saturday 10:00 to 15:00. We cut, colour and style. Bookings are made through our booking system. For gift cards, ask for reception.",
        "languages": list(LANGUAGES.items()),
    }
    module = {
        "name": "Bookings",
        "url": "https://bookings.example.com/mcp",
        "command": "",
        "args": [],
    }
    offer = probe.Offer(
        [
            ("find_free_time", "Finds the next free times for a service."),
            ("move_booking", "Moves a booking to a time that is free."),
        ]
    )
    return {"example_agent": agent, "example_module": module, "example_offer": offer}


def sees_totals(account: Any) -> bool:
    """False when `SUPER_ADMIN_EMAIL` is unset: nobody is let in."""
    return (
        bool(settings.SUPER_ADMIN_EMAIL) and account.email == settings.SUPER_ADMIN_EMAIL
    )


def origin(url: str) -> str:
    """`https://host` of an address: the form a Content-Security-Policy names."""
    return "{0.scheme}://{0.netloc}".format(urlsplit(url))


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    business = Business.objects.filter(account=request.user).first()
    return render(
        request,
        "accounts/dashboard.html",
        {
            "business": business,
            "sees_totals": sees_totals(request.user),
            "website": business and shown_domain(business.website_domain),
            "portal_origin": origin(settings.PORTAL_URL),
            "core_origin": origin(settings.CORE_URL),
            # The Business pastes this into its own website (VOI-73); only a saved domain makes it work, so only then is it shown.
            "button_html": business
            and business.website_domain
            and call_button_tag(business),
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


class Text(forms.CharField):
    """A many-line text: a browser sends each line break as two characters, so they are made one before the length is counted, as the browser counted them."""

    def to_python(self, value: Any) -> str:
        return str(super().to_python(value)).replace("\r\n", "\n").replace("\r", "\n")


FACTS_MAX: int = Business._meta.get_field("facts").max_length  # pyright: ignore[reportAssignmentType, reportAttributeAccessIssue]


class SettingsForm(forms.ModelForm):
    # The editable settings, one for one with contract/business-settings.schema.json. The AI notice is not among them.
    languages = forms.MultipleChoiceField(
        choices=list(LANGUAGES.items()),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Pick at least one language."},
    )
    facts = Text(
        required=False,
        max_length=FACTS_MAX,
        widget=forms.Textarea(attrs={"rows": 12}),
        help_text=f"Everything the agent should know about your business, in your own words: what you do, where, when you are open, what things cost. Up to {FACTS_MAX:,} characters.",
    )

    # Portal-only: the contract the core reads does not carry it. What was typed is reduced once here to the domain the database stores.
    website_domain = forms.CharField(
        label="Your website",
        required=False,
        max_length=2000,  # room for a pasted address; what is stored is at most DOMAIN_MAX
        help_text="The address of your website, for example www.example.se. Only the main domain (example.se) is kept. Leave it empty for none.",
        widget=forms.TextInput(
            attrs={
                "inputmode": "url",
                "autocomplete": "url",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        ),
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
        error_messages={
            "empty": "That file is empty. Choose your logo file and upload it again."
        },
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
        self.label_suffix = ""  # no colons, like the login and reset forms
        self.fields["name"].error_messages["required"] = "Give your business a name."
        self.fields["name"].widget.attrs["autocomplete"] = "organization"
        # The domain as its owner writes it (räksmörgås.se), not the punycode stored.
        self.initial["website_domain"] = shown_domain(self.instance.website_domain)
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

    name = forms.CharField(
        max_length=module_rules.NAME_MAX,
        error_messages={"required": "Give the Module a name."},
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    address = forms.CharField(
        max_length=module_rules.URL_MAX,
        error_messages={"required": "Give the Module's address."},
        # Not type=url: a self-hosted Portal also takes a command line here.
        widget=forms.TextInput(
            attrs={
                "inputmode": "url",
                "autocomplete": "off",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        ),
    )

    def __init__(self, *args: Any, business: Business, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
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
def remove_module(request: HttpRequest, module_id: int) -> HttpResponse:
    """The one way a Module goes: only one of the logged-in Business's own."""
    if request.method != "POST":
        return back_to("modules")
    get_object_or_404(Module, pk=module_id, business__account=request.user).delete()
    return redirect("modules")


class AccessTokenForm(forms.Form):
    """Making an Access token: a label and read-only or full."""

    label = forms.CharField(
        max_length=tokens.LABEL_MAX,
        error_messages={
            "required": "Give the token a label, such as the name of the agent that will use it."
        },
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    scope = forms.ChoiceField(
        choices=list(tokens.SCOPES.items()),
        initial="read",
        widget=forms.RadioSelect,
        error_messages={"required": "Choose read-only or full."},
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.label_suffix = ""

    def clean_label(self) -> str:
        return self.cleaned_data["label"].strip()


@login_required
@never_cache
@sensitive_variables(
    "secret", "made"
)  # a debug page or error email must never carry the secret
def access_tokens(request: HttpRequest) -> HttpResponse:
    """The Business's Access tokens, and the form to make one. The secret of a new token is on the page that answers the POST and nowhere after."""
    business = get_object_or_404(Business, account=request.user)
    form = AccessTokenForm(request.POST or None)
    made = None
    if request.method == "POST" and form.is_valid():
        _, secret = AccessToken.make(
            business,
            form.cleaned_data["label"],
            form.cleaned_data["scope"],
            sees_totals(request.user),
        )
        made = {"label": form.cleaned_data["label"], "secret": secret}
        form = AccessTokenForm()
    return render(
        request,
        "accounts/tokens.html",
        {
            "form": form,
            "made": made,
            "rows": business.access_tokens.order_by("-created_at", "-id"),  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
            "time_zone": settings.TIME_ZONE,
        },
    )


@login_required
def revoke_access_token(request: HttpRequest, token_id: int) -> HttpResponse:
    """The one way a token is revoked: only one of the logged-in Business's own, at once."""
    if request.method != "POST":
        return back_to("access_tokens")
    get_object_or_404(AccessToken, pk=token_id, business__account=request.user).revoke()
    return redirect("access_tokens")


# What a Caller reads when the call link is opened from anywhere but a frame on the Business's website, or the Business has not saved one (English; Petter approved the words on 2026-10-17 for a Business with no saved website, VOI-71; showing them for a request outside a frame (VOI-73) waits for his okay).
CALL_LINK_REFUSAL = (
    "This call can't be opened from here. Start it from the company's own website."
)


# What a Caller reads when the Business's daily budget is spent (English; Petter approved the words on 2026-10-18, VOI-123).
BUDGET_SPENT_REFUSAL = "Something went wrong. We can't take calls right now."


def call_link_refused(
    request: HttpRequest, sentence: str = CALL_LINK_REFUSAL
) -> HttpResponse:
    """The refusal as a page with its language and a heading, in the Portal's look: it shows inside the Call button's panel."""
    return render(
        request, "accounts/call_link_refused.html", {"sentence": sentence}, status=403
    )


def spent_today(business: Business) -> Decimal:
    """Today's Call link spend in dollars, the day on TIME_ZONE like the totals page. A priced record counts as priced; one the core could not price, or priced at nothing (its usage reports never came), counts its seconds at the rate Google charged this Business's priced calls so far, and at nothing before the first priced call (Petter, 2026-10-18: no invented rate). Test calls do not count, and neither does a call still open (Petter: a call may run over, the next one is refused). A budget of 0 refuses every call."""
    zone = ZoneInfo(settings.TIME_ZONE)
    today = datetime.combine(datetime.now(zone).date(), time.min, tzinfo=zone)
    records = CallRecord.objects.filter(business=business, kind="call_link")
    priced = Q(cost_usd__gt=0)
    charged = records.filter(priced).aggregate(
        usd=Sum("cost_usd"), seconds=Sum("length_seconds")
    )
    sums = records.filter(started_at__gte=today).aggregate(
        priced=Sum("cost_usd", filter=priced),
        unpriced_seconds=Sum("length_seconds", filter=~priced),
    )
    spent = sums["priced"] or Decimal(0)
    if charged["seconds"] and sums["unpriced_seconds"]:
        # Multiply before dividing: a rate rounded to 28 digits (1.00 / 300) would land just under the budget.
        spent += charged["usd"] * sums["unpriced_seconds"] / charged["seconds"]
    return spent


def to_core(business: Business, kind: str, domain: str = "") -> HttpResponse:
    """Sends a browser to the core's call page with a ticket for this one Business, the kind of call and the website allowed to frame the page: the only way a browser is let to call."""
    # Empty only on a local run; a ticket signed with nothing would be refused by the core anyway.
    if not settings.CORE_SECRET:
        return HttpResponse("Calls are not set up: CORE_SECRET is empty.", status=503)
    ticket = mint(settings.CORE_SECRET, business.pk, kind, domain)
    return redirect(f"{settings.CORE_URL.rstrip('/')}/?ticket={ticket}")


@login_required
def test_call(request: HttpRequest) -> HttpResponse:
    """A logged-in Business's own test call; it takes no Business from the request."""
    if request.method != "POST":
        return back_to("dashboard")
    return to_core(get_object_or_404(Business, account=request.user), "test")


@require_GET
@never_cache
@xframe_options_exempt  # the panel on the Business's website frames this route (VOI-73); the core's frame-ancestors keeps every other site out
def call_link(request: HttpRequest, slug: str) -> HttpResponse:
    """A Business's public call link, opened in the panel the Call button script builds on the Business's website (VOI-73).

    A ticket only goes to a browser that says it is loading a frame (`Sec-Fetch-Dest: iframe`) and only for a Business that has saved its website (VOI-71): the core then lets only that site frame the page. A missing header, as on an iPhone before iOS 16.4, is refused too. Once the Business's daily budget is spent (VOI-123), no ticket until the next day.
    """
    business = get_object_or_404(Business, call_slug=slug)
    if request.headers.get("Sec-Fetch-Dest") != "iframe":
        log.warning(
            "call link refused: Business %s opened outside a frame", business.pk
        )
        return call_link_refused(request)
    if not business.website_domain:
        log.warning("call link refused: Business %s has no website domain", business.pk)
        return call_link_refused(request)
    if spent_today(business) >= business.daily_budget_usd:
        log.warning(
            "call link refused: Business %s has spent its daily budget", business.pk
        )
        return call_link_refused(request, BUDGET_SPENT_REFUSAL)
    return to_core(business, "call_link", business.website_domain)


# The Call button script a Business's website loads, and the hash of its bytes that the pasted tag names (VOI-135):
# `make generate` writes the hash, and `make generate-check` fails when the file changed without it.
CALL_BUTTON_FILE = settings.BASE_DIR / "static" / "portal" / "call-button.v1.js"
CALL_BUTTON_INTEGRITY = (
    (settings.BASE_DIR / "call-button.v1.integrity").read_text().strip()
)
# A tag with a malformed hash (a `make generate` with no openssl writes a bare "sha384-") would be run unchecked by browsers, so the Portal refuses to start on one.
assert re.fullmatch(r"sha384-[A-Za-z0-9+/]{64}", CALL_BUTTON_INTEGRITY), (
    "portal/call-button.v1.integrity is not a sha384 hash: run make generate (it needs openssl)"
)


def tag_attributes(business: Business | None) -> dict[str, str]:
    """What the tag tells the script (its data- attributes): the core's origin, and the launcher's fill and the ring and label on it (the Theme's pair reaches AA, theme.on_accent; Voice's own for no accent or no Business)."""
    theme = business.theme() if business else {}
    return {
        "core": origin(settings.CORE_URL),
        "fill": theme.get("accent", DEEP_SEA),
        "ink": theme.get("accent_text", FOAM),
    }


def call_button_tag(business: Business) -> str:
    """The script tag the Business pastes: the versioned file with its hash, so a browser runs only that exact file (and asks for it with CORS, which WhiteNoise's `Access-Control-Allow-Origin: *` answers), and the attributes the file reads."""
    data = " ".join(f'data-{k}="{v}"' for k, v in tag_attributes(business).items())
    return (
        f'<script async src="{settings.PORTAL_URL.rstrip("/")}{static("portal/call-button.v1.js")}?business={business.call_slug}"'
        f' {data} integrity="{CALL_BUTTON_INTEGRITY}" crossorigin="anonymous"></script>'
    )


@require_GET
def call_button_js(request: HttpRequest) -> HttpResponse:
    """The script for a tag pasted before VOI-135, which carries no data attributes: the Portal writes them onto the tag in
    front of the versioned file. Its address names the Business (`?business=<call slug>`), so the launcher carries that
    Business's adjusted accent; an unknown slug, or a tag pasted before VOI-89 that names it in `data-business` instead,
    gets Voice's own look (the call link itself still decides whether a call opens)."""
    business = Business.objects.filter(
        call_slug=request.GET.get("business", "")
    ).first()
    # `?? {}`: no current script (not a classic script tag) draws nothing, as the file itself then returns.
    prelude = f"Object.assign(document.currentScript?.dataset ?? {{}}, {json.dumps(tag_attributes(business))});\n"
    return HttpResponse(
        prelude.encode() + CALL_BUTTON_FILE.read_bytes(),
        content_type="text/javascript; charset=utf-8",  # without it the page's own encoding decides how "å" reads
    )


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
