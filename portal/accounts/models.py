# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
from __future__ import annotations

import hashlib
import logging
import secrets
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, RegexValidator
from django.db import connection, models, transaction
from django.db.models.functions import Length, Lower, Now, Trim
from django.db.models.lookups import Exact, LessThanOrEqual
from django.urls import reverse

from portal.accounts import modules as module_rules
from portal.accounts import theme, tokens
from portal.accounts.domain import DOMAIN_MAX, DOMAIN_PATTERN

log = logging.getLogger(__name__)
audit = logging.getLogger("portal.audit")

# The languages a Business may pick; contract/business-settings.schema.json lists the same two (tests/portal/test_settings_contract.py).
LANGUAGES = {"sv": "Swedish", "en": "English"}

# The Business's own privacy notice for its Callers, linked from the call page beside the AI disclosure: an https address with no
# whitespace, or empty for none. contract/business-settings.schema.json carries the same rule; tests/portal/test_settings_contract.py reads both.
PRIVACY_URL_MAX = 2000
PRIVACY_URL_PATTERN = r"^https://\S+$"

# A Call record holds numbers, codes and times only; contract/call-record.schema.json lists the same kinds and patterns (tests/portal/test_call_records.py).
CALL_KINDS = {
    "test": "Test call",
    "call_link": "Call link",
    "demo": "Demo call",
    "agent_test": "Assistant's test call",
}
# Whether a kind's calls count toward the Business's daily budget (views.spent_today): a test call is exempt (VOI-123; one at a time, 10 minutes);
# a demo call (a visitor's, from the landing page, VOI-243) is a real spend and counts.
# tests/portal/test_call_link.py fails for a kind of CALL_KINDS left out here, so a new kind cannot spend uncapped (VOI-166).
# An agent test call (a link a Business's AI assistant asked for, VOI-115) counts: a token can ask for links in a loop (Petter, 2026-10-20).
BUDGET_COUNTED = {"test": False, "call_link": True, "demo": True, "agent_test": True}
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


# Every new Business's daily budget (Petter, 2026-10-18, VOI-123; DECISIONS.md).
DAILY_BUDGET_USD = Decimal(10)


def swedish_only() -> list[str]:
    return ["sv"]


# The URL-safe base64 alphabet new_call_slug writes, at its length or more: the slug goes unescaped into the Call button tag a Business pastes.
CALL_SLUG_PATTERN = r"^[A-Za-z0-9_-]{22,40}$"


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
    instructions = models.CharField(max_length=5000, blank=True, default="")
    languages = ArrayField(
        models.CharField(max_length=2, choices=list(LANGUAGES.items())),
        default=swedish_only,
    )
    # The public call link is /call/<call_slug>/; unique in the database, so one link is one Business.
    call_slug = models.CharField(max_length=40, unique=True, default=new_call_slug)
    # The registrable domain of the Business's own website, or empty for none (domain.py). Portal-only: the settings contract does not carry it.
    website_domain = models.CharField(max_length=DOMAIN_MAX, blank=True, default="")
    # US dollars of Call link calls per day (on TIME_ZONE) before the call link refuses (views.spent_today); 0 refuses every call. No Portal page sets it, so a Business cannot raise it (VOI-123). db_default: the previous Portal copy still invites while the migration runs (.claude/rules/data.md).
    # shortcut: the operator changes it from a Django shell on the Portal host, add a management command when a second Business needs its own budget
    daily_budget_usd = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=DAILY_BUDGET_USD,
        db_default=DAILY_BUDGET_USD,
    )
    # The Theme (theme.py): shown only to the Business's Callers. Empty or NULL is Voice's own look.
    logo = models.BinaryField(null=True, blank=True)
    # The logo's public address is /logo/<logo_key>/: the SHA-256 of its bytes, so it names no Business and a new logo is a new address.
    # Set only by set_logo; the database refuses a key that is not the hash of the bytes beside it.
    logo_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    accent = models.CharField(max_length=7, blank=True, default="")
    # The Business is the controller toward its Callers (docs/privacy/README.md), so the notice is its own page, linked, never text stored here.
    # db_default too: the previous Portal copy still inserts Businesses without this column while the migration runs (.claude/rules/data.md).
    privacy_url = models.CharField(
        max_length=PRIVACY_URL_MAX, blank=True, default="", db_default=""
    )

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
                condition=models.Q(privacy_url="")
                | models.Q(privacy_url__regex=PRIVACY_URL_PATTERN),
                name="business_privacy_url_must_be_empty_or_an_https_address",
            ),
            models.CheckConstraint(
                condition=models.Q(call_slug__regex=CALL_SLUG_PATTERN),
                name="business_call_slug_must_be_22_to_40_url_safe_chars",
            ),
            models.CheckConstraint(
                condition=~models.Q(name__regex=r"[\n\r]"),
                name="business_name_must_be_one_line",
            ),
            models.CheckConstraint(
                condition=models.Q(name__regex=r"\S"),
                name="business_name_must_not_be_blank",
            ),
            models.CheckConstraint(
                condition=models.Q(daily_budget_usd__gte=0),
                name="business_daily_budget_must_not_be_negative",
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
            "instructions": self.instructions,
            "languages": self.languages,
            "modules": [m.as_setting() for m in self.modules_to_serve()],
        }
        if found := self.theme():
            served["theme"] = found
        if self.privacy_url:
            served["privacy_url"] = self.privacy_url
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
    """An MCP server a Business's agent may use: its name and address only. Credentials stay inside the Module; the database refuses an address that could hold one, and a delete outside `Module.remove`."""

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

    @staticmethod
    def remove(modules: models.QuerySet[Module]) -> int:
        """The one way Modules go (the Modules page's Remove, offboarding): the database refuses any other delete (migration 0021)."""
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT set_config('voice.module_remove', 'on', true)")
            removed, _ = modules.delete()
            cursor.execute("SELECT set_config('voice.module_remove', '', true)")
        return removed

    def as_setting(self) -> dict[str, object]:
        """One item of the settings' `modules`: exactly the shape of contract/business-settings.schema.json."""
        if self.command:
            return {"name": self.name, "command": self.command, "args": self.args}
        return {"name": self.name, "url": self.url}


class CallRecord(models.Model):
    """What the core reported about one finished call. Written once and never changed: the database refuses update and delete for every role (migration 0007), and a start more than an hour ahead (0021)."""

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


class CallLog(models.Model):
    """The barge-in events of one finished call, as the core logged them (VOI-153): timings, levels and codes only.

    Final once stored, and kept 30 days after the call's start: a trigger (migration 0020) refuses UPDATE for every role and
    DELETE before then, and a check refuses an event field that `.claude/rules/security.md` does not list for a barge-in line.
    """

    # Made by the core, so a retried send is the same row.
    call_id = models.CharField(
        max_length=64, unique=True, validators=[RegexValidator(CALL_ID_PATTERN)]
    )
    business = models.ForeignKey(
        Business, on_delete=models.PROTECT, related_name="call_logs"
    )
    kind = models.CharField(max_length=20, choices=list(CALL_KINDS.items()))
    started_at = models.DateTimeField()  # UTC (USE_TZ); the expiry counts from it
    events = models.JSONField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=list(CALL_KINDS)),
                name="call_log_kind_must_be_a_known_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(call_id__regex=CALL_ID_PATTERN),
                name="call_log_id_must_be_a_plain_code",
            ),
        ]


def operator_account(account: Account) -> bool:
    """Whether `SUPER_ADMIN_EMAIL` names this Account: the totals page, the operator's Commands and their staged invites. None while unset."""
    return (
        bool(settings.SUPER_ADMIN_EMAIL) and account.email == settings.SUPER_ADMIN_EMAIL
    )


class AccessToken(models.Model):
    """What lets a Business's own agent act for it (ADR 0003). The secret is shown once and never stored, only its SHA-256. Once made, only `last_used_at`, a first `revoked_at` and offboarding's blanking of a revoked label can change, and it is never deleted: triggers (migrations 0014, 0021, 0022) refuse the rest, for every role."""

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="access_tokens"
    )
    label = models.CharField(max_length=tokens.LABEL_MAX)
    scope = models.CharField(max_length=10, choices=list(tokens.SCOPES.items()))
    # Set at creation from the Account that made it; an operator Command also needs `SUPER_ADMIN_EMAIL` to name that Account at each use (operator_account).
    is_operator = models.BooleanField(default=False)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(
        auto_now_add=True
    )  # UTC (USE_TZ), like every stored time
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    # A token from a sign-in (VOI-119) belongs to its connection and expires; a pasted token has neither.
    connection = models.ForeignKey(
        "OAuthConnection",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="access_tokens",
    )
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(scope__in=list(tokens.SCOPES)),
                name="access_token_scope_must_be_read_or_full",
            ),
            models.CheckConstraint(
                condition=models.Q(token_hash__regex=tokens.HASH_PATTERN),
                name="access_token_must_hold_a_sha256_hash_never_the_secret",
            ),
            models.CheckConstraint(
                condition=models.Q(connection__isnull=True, expires_at__isnull=True)
                | models.Q(connection__isnull=False, expires_at__isnull=False),
                name="access_token_from_a_sign_in_expires_and_only_it",
            ),
            models.CheckConstraint(
                condition=models.Q(label__regex=r"\S"),
                name="access_token_label_must_not_be_blank",
            ),
        ]

    def __str__(self) -> str:
        return self.label

    @classmethod
    def make(
        cls, business: Business, label: str, scope: str, is_operator: bool
    ) -> tuple[AccessToken, str]:
        """The one way a token is made (the Access tokens page): the token and its secret, which nothing else keeps."""
        secret = tokens.new_secret()
        made = cls.objects.create(
            business=business,
            label=label,
            scope=scope,
            is_operator=is_operator,
            token_hash=tokens.hash_of(secret),
        )
        return made, secret

    def revoke(self) -> None:
        """The one way a token stops working (the Access tokens page, offboarding). The database sets the time (its own clock, refused if any other) and a revoked token stays revoked.
        The changes it asked for that still wait are cancelled with it, so a leaked token's asks die when it does (VOI-239)."""
        with transaction.atomic(), connection.cursor() as cursor:
            type(self).objects.filter(pk=self.pk, revoked_at__isnull=True).update(
                revoked_at=Now()
            )
            # Each change's row lock orders this against an approval in flight: whichever decides first wins, the other is refused.
            cursor.execute("SELECT set_config('voice.change_decide', 'on', true)")
            # Only the rows this revoke cancelled: an approval that won a change's row lock is not one of them.
            cursor.execute(
                "UPDATE accounts_pendingchange SET decision = 'cancelled', decided_at = statement_timestamp()"
                " WHERE token_id = %s AND decision = '' RETURNING id",
                [self.pk],
            )
            cancelled = sorted(row[0] for row in cursor.fetchall())
            cursor.execute("SELECT set_config('voice.change_decide', '', true)")
            StagedValues.objects.filter(change__in=cancelled).delete()
        if cancelled:
            audit.info(
                "cancelled pending changes %s with the revoke of token %s",
                cancelled,
                self.pk,
            )


# How a Command ended. A Command refused for its token is recorded too; an unknown one never reaches a Command, so it is not.
COMMAND_RESULTS = {
    "done": "Done",
    "staged": "Staged",  # a destructive Command's change waits for the Business's approval (PendingChange)
    "refused": "Refused",
    "failed": "Failed",
    "timed_out": "Timed out",
}
COMMAND_NAME_PATTERN = r"^[a-z_]{1,64}$"


class CommandRecord(models.Model):
    """One Command a Business's own assistant sent (ADR 0003): which, with which token, when and how it ended, never its values. Written once: a trigger (migration 0025) refuses UPDATE and DELETE for every role."""

    token = models.ForeignKey(
        AccessToken, on_delete=models.PROTECT, related_name="command_records"
    )
    command = models.CharField(
        max_length=64, validators=[RegexValidator(COMMAND_NAME_PATTERN)]
    )
    sent_at = models.DateTimeField(db_default=Now())  # the database's clock, UTC
    result = models.CharField(max_length=10, choices=list(COMMAND_RESULTS.items()))

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(result__in=list(COMMAND_RESULTS)),
                name="command_record_result_must_be_a_known_result",
            ),
            models.CheckConstraint(
                condition=models.Q(command__regex=COMMAND_NAME_PATTERN),
                name="command_record_command_must_be_a_command_name",
            ),
        ]


# What a destructive Command may stage. tests/portal/test_pending_changes.py fails until a new kind is also in changes.Kind and changes.RISK, where the closed matches handle it.
CHANGE_KINDS = {
    "remove_module": "Remove a Module",
    "change_details": "Change the name, instructions or languages",
    "invite_business": "Invite a Business",
}
CHANGE_DECISIONS = {
    "approved": "Approved",
    "rejected": "Rejected",
    "cancelled": "Cancelled",  # its token was revoked (AccessToken.revoke)
}


class PendingChange(models.Model):
    """A destructive Command's change, waiting for the Business to approve or reject it in the Portal (VOI-239). Only an approval applies it, once: triggers (migration 0026) refuse a second decision, an approval after the change expired, any other change to it and its delete, for every role."""

    token = models.ForeignKey(
        AccessToken, on_delete=models.PROTECT, related_name="pending_changes"
    )  # the token that staged it; its Business is the one that decides
    kind = models.CharField(max_length=20, choices=list(CHANGE_KINDS.items()))
    target = models.JSONField()  # the id of what the change names, such as {"module": 5}; never a name (offboarding could not remove it)
    staged_at = models.DateTimeField(db_default=Now())  # the database's clock, UTC
    decision = models.CharField(
        max_length=10, choices=list(CHANGE_DECISIONS.items()), blank=True, default=""
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=list(CHANGE_KINDS)),
                name="pending_change_kind_must_be_a_known_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(decision__in=["", *CHANGE_DECISIONS]),
                name="pending_change_decision_must_be_a_known_decision",
            ),
            models.CheckConstraint(
                condition=models.Q(decision="", decided_at__isnull=True)
                | (~models.Q(decision="") & models.Q(decided_at__isnull=False)),
                name="pending_change_is_decided_with_its_time",
            ),
        ]


class StagedValues(models.Model):
    """What a staged settings change would write (VOI-113): a name or instructions may be personal data, so they live apart from
    their PendingChange, which is kept for good. Deleted once the change is decided or cancelled, or its Business offboarded; never
    changed, deleted only once the change is decided, and added only to a change that waits (triggers, migration 0028), so what is approved is what was shown."""

    change = models.OneToOneField(
        PendingChange,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="staged_values",
    )
    # The settings page's own field names, such as {"name": "..."}.
    # shortcut: an expired change's values stay until its token's revoke or offboarding; add a sweep if they pile up.
    values = models.JSONField()


# Sign-in with a click (VOI-119): the Portal is the OAuth authorization server for the agent endpoint (portal/accounts/oauth.py).
OAUTH_AUTH_METHODS = {
    "none": "Public client (PKCE)",
    "client_secret_post": "Secret in the body",
    "client_secret_basic": "Secret in the header",
}


class OAuthClient(models.Model):
    """An AI assistant's app, registered by itself (RFC 7591): anyone may register, so the consent page names it and where it
    sends the person back, and nothing here grants anything until a Business approves."""

    client_id = models.CharField(max_length=64, unique=True)
    secret_hash = models.CharField(
        max_length=64, blank=True, default=""
    )  # SHA-256; empty for a public client
    client_name = models.CharField(max_length=100)
    redirect_uris = ArrayField(models.CharField(max_length=2000), size=5)
    auth_method = models.CharField(
        max_length=20, choices=list(OAUTH_AUTH_METHODS.items())
    )
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(auth_method__in=list(OAUTH_AUTH_METHODS)),
                name="oauth_client_auth_method_must_be_known",
            ),
            models.CheckConstraint(
                condition=models.Q(auth_method="none", secret_hash="")
                | (
                    ~models.Q(auth_method="none")
                    & models.Q(secret_hash__regex=tokens.HASH_PATTERN)
                ),
                name="oauth_client_has_a_hashed_secret_unless_public",
            ),
            models.CheckConstraint(
                condition=models.Q(redirect_uris__len__gte=1),
                name="oauth_client_has_a_redirect_uri",
            ),
        ]


class OAuthCode(models.Model):
    """One approval on the consent page, exchanged once for tokens within CODE_SECONDS (oauth.py); the code itself is never stored."""

    code_hash = models.CharField(max_length=64, unique=True)
    client = models.ForeignKey(
        OAuthClient, on_delete=models.CASCADE, related_name="codes"
    )
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="oauth_codes"
    )
    scope = models.CharField(max_length=10, choices=list(tokens.SCOPES.items()))
    redirect_uri = models.CharField(max_length=2000)
    code_challenge = models.CharField(max_length=128)
    created_at = models.DateTimeField(db_default=Now())
    used_at = models.DateTimeField(null=True, blank=True)


class OAuthConnection(models.Model):
    """A Business's sign-in from one AI assistant: it lasts until revoked on the Access tokens page, and renews its short-lived
    Access tokens with a refresh token that changes at every use (only its hash is kept)."""

    business = models.ForeignKey(
        Business, on_delete=models.PROTECT, related_name="oauth_connections"
    )
    client = models.ForeignKey(
        OAuthClient, on_delete=models.PROTECT, related_name="connections"
    )
    scope = models.CharField(max_length=10, choices=list(tokens.SCOPES.items()))
    refresh_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(db_default=Now())
    revoked_at = models.DateTimeField(null=True, blank=True)

    def revoke(self) -> None:
        """The one way a connection ends (the Access tokens page, offboarding): it and every token it gave stop working."""
        with transaction.atomic():
            type(self).objects.filter(pk=self.pk, revoked_at__isnull=True).update(
                revoked_at=Now()
            )
            for token in self.access_tokens.filter(revoked_at__isnull=True):  # pyright: ignore[reportAttributeAccessIssue]
                token.revoke()
