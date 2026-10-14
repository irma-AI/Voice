# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
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
    if Account.objects.filter(email=clean_email(email)).exists():
        raise ValueError(
            "that email already has an account: its owner can use Forgot your password"
        )
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
            {"name": name, "link": settings.PORTAL_URL.rstrip("/") + path},
        ),
        None,
        [account.email],
    )
    return account
