# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.functions import Lower, Trim

from portal.accounts import modules as module_rules

log = logging.getLogger(__name__)

# The languages a Business may pick; contract/business-settings.schema.json lists the same two (tests/portal/test_settings_contract.py).
LANGUAGES = {"sv": "Swedish", "en": "English"}


def swedish_only() -> list[str]:
    return ["sv"]


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

    def as_settings(self) -> dict[str, object]:
        """What the settings address serves: exactly the properties of contract/business-settings.schema.json."""
        return {
            "name": self.name,
            "facts": self.facts,
            "languages": self.languages,
            "modules": [m.as_setting() for m in self.modules_to_serve()],
        }

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
