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


def invite(name: str, email: str) -> Account:
    """The one way an invite is sent: create the Business and its Account (no password yet) and email the link to set one.

    An email that already has an account is refused; its owner uses "forgot your password", which also covers an expired invite.
    """
    email = clean_email(email)
    try:
        validate_email(email)
    except ValidationError:
        raise ValueError("that is not an email address") from None
    if not name.strip():
        raise ValueError("a Business needs a name")
    if Account.objects.filter(email=email).exists():
        raise ValueError(
            "that email already has an account: its owner can use Forgot your password"
        )
    # Mail goes inside the transaction: a failed send leaves no account behind. The error names no address (security.md).
    try:
        with transaction.atomic():
            account = Account.objects.create_user(email)
            Business.objects.create(account=account, name=name.strip())
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
                        "name": name.strip(),
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
