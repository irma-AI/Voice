# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""The Modules page's form: the one place a Module is checked and added, by the page and by the agent's Commands (VOI-114)."""

from typing import Any

from django import forms
from django.conf import settings
from django.db import IntegrityError, transaction

from portal.accounts import modules as module_rules
from portal.accounts.models import Business, Module


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

    def add(self) -> Module | None:
        """The one way a Module is added, by the Modules page and the agent's add_module: the Module, or None with the
        database's refusal (the ten-per-Business limit, or a name taken a moment ago) on the form."""
        try:
            with transaction.atomic():
                return self._create()
        except IntegrityError:
            self.add_error(
                None,
                f"The Module was not added: a Business has at most {module_rules.MODULES_MAX} Modules, with different names.",
            )
            return None

    def _create(self) -> Module:
        url, command, args = self.cleaned_data["address"]
        return Module.objects.create(
            business=self.business,
            name=self.cleaned_data["name"],
            url=url,
            command=command,
            args=args,
        )
