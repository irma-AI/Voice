"""Helpers the Portal tests share."""

from django.test import Client

from portal.accounts.models import Account, Business

PASSWORD = "a-long-passphrase-for-tests"


def business_with_login(email: str, name: str) -> tuple[Business, Client]:
    """A Business with its Account, and a test client logged in as it."""
    account = Account.objects.create_user(email, PASSWORD)
    business = Business.objects.create(account=account, name=name)
    client = Client()
    assert client.login(email=email, password=PASSWORD)
    return business, client
