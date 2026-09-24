"""A provider key is sealed under the server secret and opens only in its own row."""

from __future__ import annotations

from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import SecretStr

from pathfinder.platform.provider_key_cipher import (
    ProviderKeyCipher,
    hint_for,
    key_aad,
)

_SENTINEL = "sk-proj-sentinel-0123456789WXYZ"
_SECRET = bytes(range(32))


def _cipher() -> ProviderKeyCipher:
    return ProviderKeyCipher(secret=_SECRET)


def _aad(provider: str = "openai") -> bytes:
    return key_aad(_USER, "pathfinder", provider)


_USER = uuid4()


def test_a_sealed_key_opens_to_the_same_key() -> None:
    blob = _cipher().seal(SecretStr(_SENTINEL), aad=_aad())

    assert _cipher().open(blob, aad=_aad()).get_secret_value() == _SENTINEL


def test_the_blob_holds_no_part_of_the_key() -> None:
    blob = _cipher().seal(SecretStr(_SENTINEL), aad=_aad())

    assert _SENTINEL.encode() not in blob
    assert b"WXYZ" not in blob


def test_two_seals_of_one_key_differ() -> None:
    first = _cipher().seal(SecretStr(_SENTINEL), aad=_aad())
    second = _cipher().seal(SecretStr(_SENTINEL), aad=_aad())

    assert first != second


@pytest.mark.parametrize(
    "other",
    [
        key_aad(uuid4(), "pathfinder", "openai"),
        key_aad(_USER, "companion", "openai"),
        key_aad(_USER, "pathfinder", "anthropic"),
    ],
    ids=["another user", "another application", "another provider"],
)
def test_a_blob_copied_into_another_row_does_not_open(other: bytes) -> None:
    blob = _cipher().seal(SecretStr(_SENTINEL), aad=_aad())

    with pytest.raises(InvalidTag):
        _cipher().open(blob, aad=other)


def test_one_flipped_byte_does_not_open() -> None:
    blob = bytearray(_cipher().seal(SecretStr(_SENTINEL), aad=_aad()))
    blob[-1] ^= 0x01

    with pytest.raises(InvalidTag):
        _cipher().open(bytes(blob), aad=_aad())


def test_another_secret_does_not_open_the_blob() -> None:
    blob = _cipher().seal(SecretStr(_SENTINEL), aad=_aad())

    with pytest.raises(InvalidTag):
        ProviderKeyCipher(secret=bytes(32)).open(blob, aad=_aad())


def test_the_hint_is_the_last_four_characters() -> None:
    assert hint_for(SecretStr(_SENTINEL)) == "WXYZ"


def test_the_cipher_never_prints_its_secret() -> None:
    assert repr(_cipher()) == "ProviderKeyCipher()"
