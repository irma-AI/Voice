# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
from __future__ import annotations

import hashlib
import logging
import secrets

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Length, Lower, Trim
from django.db.models.lookups import Exact, LessThanOrEqual
from django.urls import reverse

from portal.accounts import modules as module_rules
from portal.accounts import theme
from portal.accounts.domain import DOMAIN_MAX, DOMAIN_PATTERN

log = logging.getLogger(__name__)

# The languages a Business may pick; contract/business-settings.schema.json lists the same two (tests/portal/test_settings_contract.py).
LANGUAGES = {"sv": "Swedish", "en": "English"}

# A Call record holds numbers, codes and times only; contract/call-record.schema.json lists the same kinds and patterns (tests/portal/test_call_records.py).
CALL_KINDS = {"test": "Test call", "call_link": "Call link"}
CALL_ID_PATTERN = r"^[A-Za-z0-9-]{8,64}$"
COST_REASON_PATTERN = r"^[a-z_]{1,60}$"


def _logo_is_png_webp_or_jpeg() -> models.Q:
    """True in Postgres when the logo's bytes start like one of theme.LOGO_SIGNATURES: the type is read from the bytes."""

    def starts(at: int, magic: bytes) -> Exact:
        part = models.Func(
            models.F("logo"),
            models.Value(at + 1),
            models.Value(len(magic)),
            function="SUBSTRING",
            output_field=models.BinaryField(),
        )
        return Exact(part, models.Value(magic, output_field=models.BinaryField()))

    either = models.Q()
    for parts in theme.LOGO_SIGNATURES.values():
        either |= models.Q(*(starts(at, magic) for at, magic in parts))
    return either


def _hash_of_the_logo() -> models.Func:
    return models.Func(
        models.Func(
            models.F("logo"), function="SHA256", output_field=models.BinaryField()
        ),
        models.Value("hex"),
        function="ENCODE",
        output_field=models.CharField(),
    )


def swedish_only() -> list[str]:
    return ["sv"]


def new_call_slug() -> str:
    """The unguessable part of a Business's public call link."""
    return secrets.token_urlsafe(16)


def clean_email(email: str) -> str:
    """The one spelling an email is stored and looked up in: trimmed and lower case (the database refuses any other)."""
    return email.strip().lower()


class AccountManager(BaseUserManager["Account"]):
    def create_user(self, email: str, password: str | None = None) -> Account:
        account = self.model(email=clean_email(email))
        account.set_password(
            password
        )  # None leaves the password unusable until the invite is accepted
        account.save(using=self._db)
        return account


class Account(AbstractBaseUser):
    """A login. An invited Business gets one Account and one Business together (invite.py); the Business points at its Account."""

    email = models.EmailField(unique=True)
    is_active = models.BooleanField(
        default=True
    )  # Django's password reset only emails active accounts

    USERNAME_FIELD = "email"
    objects = AccountManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(email=Lower(Trim("email"))),
                name="account_email_must_be_clean",
            ),
        ]


class Business(models.Model):
    account = models.OneToOneField(
        Account, on_delete=models.PROTECT, related_name="business"
    )
    name = models.CharField(max_length=200)
    facts = models.CharField(max_length=5000, blank=True, default="")
    languages = ArrayField(
        models.CharField(max_length=2, choices=list(LANGUAGES.items())),
        default=swedish_only,
    )
    # The public call link is /call/<call_slug>/; unique in the database, so one link is one Business.
    call_slug = models.CharField(max_length=40, unique=True, default=new_call_slug)
    # The registrable domain of the Business's own website, or empty for none (domain.py). Portal-only: the settings contract does not carry it.
    website_domain = models.CharField(max_length=DOMAIN_MAX, blank=True, default="")
    # The Theme (theme.py): shown only to the Business's Callers. Empty or NULL is Voice's own look.
    logo = models.BinaryField(null=True, blank=True)
    # The logo's public address is /logo/<logo_key>/: the SHA-256 of its bytes, so it names no Business and a new logo is a new address.
    # Set only by set_logo; the database refuses a key that is not the hash of the bytes beside it.
    logo_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    accent = models.CharField(max_length=7, blank=True, default="")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(logo__isnull=True)
                | models.Q(LessThanOrEqual(Length("logo"), theme.LOGO_MAX_BYTES)),
                name=f"business_logo_must_be_at_most_{theme.LOGO_MAX_BYTES // 1024}_kb",
            ),
            models.CheckConstraint(
                condition=models.Q(logo__isnull=True) | _logo_is_png_webp_or_jpeg(),
                name="business_logo_must_be_png_webp_or_jpeg",
            ),
            models.CheckConstraint(
                condition=(models.Q(logo__isnull=True) & models.Q(logo_key=""))
                | models.Q(
                    models.Q(logo__isnull=False),
                    Exact(models.F("logo_key"), _hash_of_the_logo()),
                ),
                name="business_logo_key_must_be_the_sha256_of_the_logo_use_set_logo",
            ),
            models.CheckConstraint(
                condition=models.Q(accent="")
                | models.Q(accent__regex=theme.ACCENT_PATTERN),
                name="business_accent_must_be_empty_or_a_six_digit_hex_colour",
            ),
            models.CheckConstraint(
                condition=models.Q(website_domain="")
                | models.Q(website_domain__regex=DOMAIN_PATTERN),
                name="business_website_domain_must_be_empty_or_a_clean_domain",
            ),
            models.CheckConstraint(
                condition=models.Q(name__regex=r"\S"),
                name="business_name_must_not_be_blank",
            ),
            models.CheckConstraint(
                condition=models.Q(languages__len__gte=1)
                & models.Q(languages__contained_by=list(LANGUAGES)),
                name="business_languages_must_be_one_or_more_known",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def as_settings(self) -> dict[str, object]:
        """What the settings address serves: exactly the properties of contract/business-settings.schema.json."""
        served: dict[str, object] = {
            "name": self.name,
            "facts": self.facts,
            "languages": self.languages,
            "modules": [m.as_setting() for m in self.modules_to_serve()],
        }
        if found := self.theme():
            served["theme"] = found
        return served

    def set_logo(self, data: bytes | None) -> None:
        """The one way a logo and its key change together (save() writes them); None removes the logo."""
        self.logo = data
        self.logo_key = hashlib.sha256(data).hexdigest() if data is not None else ""

    def theme(self) -> dict[str, str]:
        """The contract's `theme`: the accent as Callers see it (adjusted for AA at each read, theme.on_accent) with the text it carries, and the logo's public address. Empty for Voice's own look."""
        found: dict[str, str] = {}
        if self.accent:
            found["accent"], found["accent_text"] = theme.on_accent(self.accent)
        if self.logo_key:
            found["logo_url"] = settings.PORTAL_URL.rstrip("/") + reverse(
                "logo", args=[self.logo_key]
            )
        return found

    def modules_to_serve(self) -> list[Module]:
        """The Modules the core is told about. A local one is left out unless self-hosting allows it: the settings check itself, whatever wrote the row."""
        served: list[Module] = []
        for module in self.modules.order_by("id"):  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
            if module.command and not settings.ALLOW_LOCAL_MODULES:
                log.error(
                    "Module %s of Business %s is local and not allowed here, so it is not served",
                    module.pk,
                    self.pk,
                )
                continue
            served.append(module)
        return served


class Module(models.Model):
    """An MCP server a Business's agent may use: its name and address only. Credentials stay inside the Module; the database refuses an address that could hold one."""

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="modules"
    )
    name = models.CharField(max_length=module_rules.NAME_MAX)
    url = models.CharField(max_length=module_rules.URL_MAX, blank=True, default="")
    command = models.CharField(
        max_length=module_rules.COMMAND_MAX, blank=True, default=""
    )
    args = ArrayField(
        models.CharField(max_length=module_rules.ARG_MAX),
        blank=True,
        default=list,
    )

    class Meta:
        # At most MODULES_MAX per Business is a trigger in migration 0004: a count cannot be a constraint.
        constraints = [
            models.UniqueConstraint(
                fields=["business", "name"],
                name="module_name_must_be_unique_per_business",
            ),
            models.CheckConstraint(
                condition=models.Q(name__regex=r"\S"),
                name="module_name_must_not_be_blank",
            ),
            models.CheckConstraint(
                condition=(models.Q(url="") & ~models.Q(command=""))
                | (~models.Q(url="") & models.Q(command="") & models.Q(args__len=0)),
                name="module_must_have_an_address_or_a_command_not_both",
            ),
            models.CheckConstraint(
                condition=models.Q(url="")
                | models.Q(url__regex=module_rules.URL_PATTERN),
                name="module_address_must_be_plain_with_no_password_or_key",
            ),
            models.CheckConstraint(
                condition=models.Q(args__len__lte=module_rules.ARGS_MAX),
                name="module_must_have_at_most_20_args",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def as_setting(self) -> dict[str, object]:
        """One item of the settings' `modules`: exactly the shape of contract/business-settings.schema.json."""
        if self.command:
            return {"name": self.name, "command": self.command, "args": self.args}
        return {"name": self.name, "url": self.url}


class CallRecord(models.Model):
    """What the core reported about one finished call. Written once and never changed: the database refuses update and delete for every role (migration 0007)."""

    # Made by the core, so a retried send is the same row.
    call_id = models.CharField(
        max_length=64, unique=True, validators=[RegexValidator(CALL_ID_PATTERN)]
    )
    business = models.ForeignKey(
        Business, on_delete=models.PROTECT, related_name="call_records"
    )
    kind = models.CharField(max_length=20, choices=list(CALL_KINDS.items()))
    started_at = models.DateTimeField()  # UTC (USE_TZ), like every stored time
    length_seconds = models.PositiveIntegerField()
    prompt_tokens = models.PositiveIntegerField()
    completion_tokens = models.PositiveIntegerField()
    input_audio_tokens = models.PositiveIntegerField()
    output_audio_tokens = models.PositiveIntegerField()
    thinking_tokens = models.PositiveIntegerField()
    cached_tokens = models.PositiveIntegerField()
    # US dollars, Google's own currency; empty with a reason when the core could not work it out.
    cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    price_date = models.DateField(null=True, blank=True)
    cost_reason = models.CharField(
        max_length=60,
        blank=True,
        default="",
        validators=[RegexValidator(COST_REASON_PATTERN)],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=list(CALL_KINDS)),
                name="call_record_kind_must_be_a_known_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(call_id__regex=CALL_ID_PATTERN),
                name="call_record_id_must_be_a_plain_code",
            ),
            models.CheckConstraint(
                condition=models.Q(cost_usd__gte=0) | models.Q(cost_usd__isnull=True),
                name="call_record_cost_must_not_be_negative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(cost_usd__isnull=False)
                    & models.Q(price_date__isnull=False)
                    & models.Q(cost_reason="")
                )
                | (
                    models.Q(cost_usd__isnull=True)
                    & models.Q(cost_reason__regex=COST_REASON_PATTERN)
                ),
                name="call_record_has_a_cost_with_its_price_date_or_a_reason_for_none",
            ),
        ]
