# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""The settings page's form: the one place a Business's settings are checked and written, by the page and by the agent's Commands (VOI-113)."""

import re
from typing import Any

from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile

from portal.accounts.domain import parse_domain, shown_domain
from portal.accounts.models import (
    LANGUAGES,
    PRIVACY_URL_MAX,
    PRIVACY_URL_PATTERN,
    Business,
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


class Text(forms.CharField):
    """A many-line text: a browser sends each line break as two characters, so they are made one before the length is counted, as the browser counted them."""

    def to_python(self, value: Any) -> str:
        return str(super().to_python(value)).replace("\r\n", "\n").replace("\r", "\n")


INSTRUCTIONS_MAX: int = Business._meta.get_field("instructions").max_length  # pyright: ignore[reportAssignmentType, reportAttributeAccessIssue]


# The settings a page left open could hold stale: each is sent with the value the page showed.
SHOWN = (
    "name",
    "instructions",
    "languages",
    "website_domain",
    "privacy_url",
    "use_accent",
    "accent",
)


class SettingsForm(forms.ModelForm):
    # The editable settings, one for one with contract/business-settings.schema.json. The AI notice is not among them.
    languages = forms.MultipleChoiceField(
        choices=list(LANGUAGES.items()),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Pick at least one language."},
    )
    instructions = Text(
        required=False,
        max_length=INSTRUCTIONS_MAX,
        widget=forms.Textarea(attrs={"rows": 12}),
        help_text=f"Everything the agent should know about your business, in your own words: what you do, where, when you are open, what things cost. Up to {INSTRUCTIONS_MAX:,} characters.",
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

    # The Business's own privacy notice: the call page links it beside the AI disclosure (the Business is the controller toward its Callers).
    privacy_url = forms.URLField(
        label="Your privacy notice",
        required=False,
        max_length=PRIVACY_URL_MAX,
        assume_scheme="https",
        help_text="The address of your privacy notice for your Callers, for example https://www.example.se/privacy. Your Callers see a link to it on the call page. Leave it empty for none.",
        widget=forms.URLInput(
            attrs={
                "autocomplete": "url",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        ),
    )

    def clean_privacy_url(self) -> str:
        url: str = self.cleaned_data["privacy_url"]
        if url and not re.fullmatch(PRIVACY_URL_PATTERN, url):
            raise forms.ValidationError(
                "That is not an https address. Type the address of your privacy notice, starting with https://."
            )
        return url

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
        # The page sends what it showed, so save() writes only what this person changed (VOI-113: Commands write too).
        for name in SHOWN:
            self.fields[name].show_hidden_initial = True

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

    def clean_name(self) -> str:
        name: str = self.cleaned_data["name"]
        if (
            "\n" in name or "\r" in name
        ):  # a preview line break could pass the rest off as another change
            raise forms.ValidationError("Write your business's name on one line.")
        return name

    def edited(self, name: str) -> bool:
        """Changed from what the page showed; with no record of that (a request built by hand), always."""
        return (
            name in self.changed_data or self.add_initial_prefix(name) not in self.data
        )

    def save(self, commit: bool = True) -> Business:
        """Writes only what this form changed from what it showed, so a page left open does not undo a change made since."""
        business: Business = super().save(commit=False)
        fields = [f for f in self._meta.fields or () if self.edited(f)]
        if self.cleaned_data["logo"] is not None:
            business.set_logo(self.cleaned_data["logo"])
            fields += ["logo", "logo_key"]
        elif self.cleaned_data["remove_logo"]:
            business.set_logo(None)
            fields += ["logo", "logo_key"]
        if self.edited("use_accent") or self.edited("accent"):
            business.accent = self.cleaned_data["accent"]
            fields.append("accent")
        if commit and fields:
            business.save(update_fields=fields)
        return business

    class Meta:
        model = Business
        fields = ("name", "instructions", "languages", "website_domain", "privacy_url")


def changed(
    business: Business, logo: bytes | None = None, **fields: Any
) -> SettingsForm:
    """The page's form filled as the page shows it, with `fields` (the page's own field names) and a logo upload on top:
    a Command's way through the page's rules, so the same input is stored and refused the same way."""
    shown = {
        "name": business.name,
        "instructions": business.instructions,
        "languages": business.languages,
        "website_domain": shown_domain(business.website_domain),
        "privacy_url": business.privacy_url,
        "use_accent": "on" if business.accent else "",
        "accent": business.accent,
    }
    data = {**shown, **{f"initial-{k}": v for k, v in shown.items()}, **fields}
    files = None if logo is None else {"logo": SimpleUploadedFile("logo", logo)}
    return SettingsForm(data, files, instance=business)


def problems(form: forms.BaseForm) -> str:
    """A refused form's sentences, as the page shows them."""
    return " ".join(str(m) for errors in form.errors.values() for m in errors)
