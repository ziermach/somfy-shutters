"""T004: tokens and pairing codes as strings."""

from __future__ import annotations

import pytest

from somfy_shutters.auth.tokens import (
    ALPHABET,
    digest,
    format_code,
    looks_like_token,
    new_code,
    new_token,
    normalise_code,
)


def test_token_shape() -> None:
    token = new_token()
    assert token.startswith("sst_") and len(token) == 56
    assert all(c in ALPHABET for c in token[4:])
    assert looks_like_token(token)


def test_alphabet_has_no_ambiguous_letters() -> None:
    assert len(ALPHABET) == 32
    assert not set("ILOU") & set(ALPHABET)


def test_thousand_tokens_are_distinct() -> None:
    assert len({new_token() for _ in range(1000)}) == 1000


@pytest.mark.parametrize(
    "value", ["", "sst_", "sst_" + "A" * 51, "xyz_" + "A" * 52, "sst_" + "I" * 52]
)
def test_not_a_token(value: str) -> None:
    assert not looks_like_token(value)


def test_code_shape_and_format() -> None:
    code = new_code()
    assert len(code) == 6 and all(c in ALPHABET for c in code)
    assert format_code("K7Q9XM") == "K7Q-9XM"


@pytest.mark.parametrize("typed", ["k7q-9xm", " K7Q9XM ", "k7q 9xm", "K7Q-9XM"])
def test_codes_are_read_the_way_people_type_them(typed: str) -> None:
    assert normalise_code(typed) == "K7Q9XM"


@pytest.mark.parametrize("typed", ["K7Q9X", "K7Q9XMM", "K7Q9XI", "K7Q9XÖ", ""])
def test_not_a_code(typed: str) -> None:
    assert normalise_code(typed) is None


def test_digest_is_stable_and_hides_the_value() -> None:
    assert digest("sst_x") == digest("sst_x")
    assert len(digest("sst_x")) == 64 and "sst_x" not in digest("sst_x")
