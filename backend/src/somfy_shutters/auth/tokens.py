"""Credentials and pairing codes as strings (specs/007-api-auth-audit/research.md §1, §7).

Pure: nothing here stores or compares anything. A credential is 256 random bits,
so a plain SHA-256 is the right way to keep it — a slow password hash would only
make every request slower on a Pi without making a guess any likelier.
"""

from __future__ import annotations

import hashlib
import secrets

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
"""Crockford base32: no I, L, O or U, so nothing reads as a 1, a 0 or a V."""

TOKEN_PREFIX = "sst_"
TOKEN_BYTES = 32
TOKEN_CHARS = 52  # ceil(256 / 5)
CODE_CHARS = 6


def _base32(data: bytes, length: int) -> str:
    number = int.from_bytes(data, "big")
    out = []
    for _ in range(length):
        number, rest = divmod(number, 32)
        out.append(ALPHABET[rest])
    return "".join(reversed(out))


def new_token() -> str:
    """The prefix and 52 characters. The prefix makes a leaked one recognisable in a paste."""
    return TOKEN_PREFIX + _base32(secrets.token_bytes(TOKEN_BYTES), TOKEN_CHARS)


def looks_like_token(value: str) -> bool:
    body = value[len(TOKEN_PREFIX) :]
    return (
        value.startswith(TOKEN_PREFIX)
        and len(body) == TOKEN_CHARS
        and all(c in ALPHABET for c in body)
    )


def new_code() -> str:
    """Six characters, short enough to read out across a room (FR-033)."""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_CHARS))


def format_code(code: str) -> str:
    return f"{code[:3]}-{code[3:]}"


def normalise_code(value: str) -> str | None:
    """What a person typed, as the six characters it means — or None."""
    cleaned = value.replace("-", "").replace(" ", "").upper()
    if len(cleaned) != CODE_CHARS or any(c not in ALPHABET for c in cleaned):
        return None
    return cleaned


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
