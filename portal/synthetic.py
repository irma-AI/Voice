"""The one way synthetic people and Businesses are made (VOI-259): `make seed` and the Portal tests both draw from here.

Every email is on example.com, reserved for examples (RFC 2606), so nothing made here can reach a real inbox.
Faker is in the `synthetic` dependency group, which neither image installs: only the seed and the tests import this module.
"""

from faker import Faker

RESERVED_DOMAIN = "example.com"
# PTS's series for books and films, in E.164: the last two digits run over each range (docs/research/swedish-fictional-phone-numbers.md).
# Faker's own sv_SE numbers are random digits and can be someone's, so it is never asked for one.
RESERVED_PHONES = tuple(
    f"{base}{last:02d}"
    for base, first in [
        ("+467017406", 5),  # 070-174 06 05..99
        ("+463139006", 0),  # 031-390 06 00..99
        ("+464062804", 0),  # 040-628 04 00..99
        ("+468465004", 0),  # 08-465 004 00..99
        ("+469803192", 0),  # 0980-319 200..99
    ]
    for last in range(first, 100)
)

fake = Faker("sv_SE")


def email() -> str:
    """A fresh email, never the same twice in one process, on a reserved domain."""
    return f"{fake.unique.user_name()}@{RESERVED_DOMAIN}"


def phone_number() -> str:
    return fake.random_element(RESERVED_PHONES)


def business_name() -> str:
    return fake.company()
