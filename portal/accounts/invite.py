# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
from smtplib import SMTPException

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from portal.accounts.models import Account, Business, clean_email


def checked(name: str, email: str) -> tuple[str, str]:
    """The name and email an invite would use, or ValueError with the reason: what invite and the agent's invite_business refuse."""
    email = clean_email(email)
    try:
        validate_email(email)
    except ValidationError:
        raise ValueError("that is not an email address") from None
    name = name.strip()
    if not name:
        raise ValueError("a Business needs a name")
    if "\n" in name or "\r" in name:
        raise ValueError("a Business's name goes on one line")
    if Account.objects.filter(email=email).exists():
        raise ValueError(
            "that email already has an account: its owner can use Forgot your password"
        )
    return name, email


def invite(name: str, email: str) -> Account:
    """The one way an invite is sent: create the Business and its Account (no password yet) and email the link to set one.

    An email that already has an account is refused; its owner uses "forgot your password", which also covers an expired invite.
    """
    name, email = checked(name, email)
    # Mail goes inside the transaction: a failed send leaves no account behind. The error names no address (security.md).
    try:
        with transaction.atomic():
            account = Account.objects.create_user(email)
            Business.objects.create(account=account, name=name)
            path = reverse(
                "password_reset_confirm",
                args=[
                    urlsafe_base64_encode(force_bytes(account.pk)),
                    default_token_generator.make_token(account),
                ],
            )
            send_mail(
                "You are invited to the Voice Portal",
                render_to_string(
                    "accounts/invite_email.txt",
                    {
                        "name": name,
                        "link": settings.PORTAL_URL.rstrip("/") + path,
                    },
                ),
                None,
                [account.email],
            )
    except (OSError, SMTPException):
        raise ValueError(
            "the invite email could not be sent, so nothing was created"
        ) from None
    return account
