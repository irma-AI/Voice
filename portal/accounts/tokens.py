"""Access tokens (ADR 0003): the secret a Business pastes into its own agent. Only the hash is stored; the secret is shown once, when it is made."""

import hashlib
import secrets

# What a token may do. A Business picks one when it makes the token; the database refuses any other value.
SCOPES = {"read": "Read-only", "full": "Full"}

LABEL_MAX = 60

# A prefix lets a secret scanner (and a Business) tell it from a password. The rest is 256 random bits, so a plain SHA-256 is enough: there is nothing to guess.
PREFIX = "voice_"

# What the database holds in place of the secret: a lower-case SHA-256 in hex.
HASH_PATTERN = r"^[0-9a-f]{64}$"


def new_secret() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def hash_of(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()
