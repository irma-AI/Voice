"""The Business's website domain: the one place a typed address becomes the registrable domain the database stores.

The registrable domain is the public suffix plus the label before it (`shop.example.se` -> `example.se`), counting the
Public Suffix List's private section, so `alice.github.io` and `bob.github.io` are two domains. The list is the snapshot
bundled in the library: no network at request time. The Portal alone holds the domain (VOI-70); the settings contract and
the call ticket do not carry it.
"""

import re
from urllib.parse import urlsplit

import idna
from publicsuffixlist import PublicSuffixList

# A plain lower-case punycode hostname of two labels or more. The database refuses anything else (models.py): a later
# ticket writes the stored value into a response header, so this strictness is what keeps that safe.
DOMAIN_PATTERN = (
    r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"
)
DOMAIN_MAX = 253

PROBLEM = "That is not a website domain. Type your website's address, for example www.example.se."

_psl = PublicSuffixList()


def registrable_domain(host: str) -> str | None:
    """The registrable domain of a host name, or None: an IP address, `localhost`, a bare public suffix, an unknown ending or anything that is not a host name."""
    try:
        ascii_host = idna.encode(host.strip().rstrip("."), uts46=True).decode(
            "ascii"
        )  # what a browser sends: UTS 46 punycode
    except idna.IDNAError:
        return None
    found = _psl.privatesuffix(ascii_host, accept_unknown=False)
    return found if found and re.fullmatch(DOMAIN_PATTERN, found) else None


def parse_domain(text: str) -> str:
    """What a Business typed (`https://www.Shop.Example.SE:8443/x`, `example.se`) as the domain to store; "" for nothing. Raises ValueError with the sentence to show."""
    text = text.strip()
    if not text:
        return ""
    try:
        host = urlsplit(text if "://" in text else f"//{text}").hostname
    except ValueError:
        host = None
    if not host or not (domain := registrable_domain(host)):
        raise ValueError(PROBLEM)
    return domain
