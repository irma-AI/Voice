# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
from __future__ import annotations

import secrets

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models.functions import Coalesce, Lower, Trim
from django.utils import timezone

# The languages a Business may pick; contract/business-settings.schema.json lists the same two (tests/portal/test_settings_contract.py).
LANGUAGES = {"sv": "Swedish", "en": "English"}


# Why the core is told to refuse a call; voice/calls.py REASONS lists the same words (tests/portal/test_calls.py holds them together).
OFF, LIMIT = "off", "limit"
# The longest a call can run: voice/serve.py MAX_CALL_SECS (tests/portal/test_calls.py). A call whose end the core never reported counts as this long.
LONGEST_CALL_SECONDS = 600


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
    max_calls_per_day = models.IntegerField(default=10)
    max_minutes_per_day = models.IntegerField(default=30)
    # Petter's switch: the core refuses every call of a Business that is off. Set only by `configure_business`, like the limits above.
    enabled = models.BooleanField(default=True)
    call_slug = models.CharField(max_length=40, unique=True, default=new_call_slug)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(name__regex=r"\S"),
                name="business_name_must_not_be_blank",
            ),
            models.CheckConstraint(
                condition=models.Q(languages__len__gte=1)
                & models.Q(languages__contained_by=list(LANGUAGES)),
                name="business_languages_must_be_one_or_more_known",
            ),
            models.CheckConstraint(
                condition=models.Q(max_calls_per_day__gte=0),
                name="business_calls_per_day_must_not_be_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(max_minutes_per_day__gte=0),
                name="business_minutes_per_day_must_not_be_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def used_today(self) -> tuple[int, int]:
        """(calls, seconds) used since 00:00 UTC. A call still running, or whose end never arrived, counts as the longest a call can be."""
        # ponytail: the day is a UTC day, so it turns over at 01:00 or 02:00 Swedish time; make it the Business's own midnight if that matters.
        since = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today = Call.objects.filter(business=self, started_at__gte=since)
        seconds = today.aggregate(
            total=models.Sum(Coalesce("seconds", models.Value(LONGEST_CALL_SECONDS)))
        )["total"]
        return today.count(), seconds or 0

    def start_call(self) -> Call | str:
        """The one way a call starts: the new Call, or the reason it is refused (OFF or LIMIT).

        The Business row is locked while the count is read and the Call written, so two calls starting together cannot both take the last slot.
        """
        with transaction.atomic():
            business = Business.objects.select_for_update().get(pk=self.pk)
            if not business.enabled:
                return OFF
            calls, seconds = business.used_today()
            if (
                calls >= business.max_calls_per_day
                or seconds >= business.max_minutes_per_day * 60
            ):
                return LIMIT
            return Call.objects.create(business=business)

    def as_settings(self) -> dict[str, object]:
        """What the settings address serves: exactly the properties of contract/business-settings.schema.json."""
        return {
            "name": self.name,
            "facts": self.facts,
            "languages": self.languages,
        }


class Call(models.Model):
    """One call the core was let start. Timings only: no words, no audio (.claude/rules/security.md)."""

    business = models.ForeignKey(
        Business, on_delete=models.PROTECT, related_name="calls"
    )
    started_at = models.DateTimeField(default=timezone.now)
    seconds = models.IntegerField(
        null=True
    )  # null until the core reports the call's end

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(seconds__isnull=True) | models.Q(seconds__gte=0),
                name="call_seconds_must_not_be_negative",
            ),
        ]
        indexes = [models.Index(fields=["business", "started_at"])]
