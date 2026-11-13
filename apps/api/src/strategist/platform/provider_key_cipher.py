"""The seal a researcher's provider key is stored under.

AES-256-GCM under the server secret. The associated data names the row's user,
application and provider, so a ciphertext copied into another row does not open.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

SECRET_BYTES = 32
_NONCE_BYTES = 12
_HINT_CHARS = 4
# The first byte of a blob names its scheme. There is one.
_SCHEME = b"\x01"


def key_aad(user_id: UUID, application_id: str, provider: str) -> bytes:
    """The associated data that binds a blob to its row."""
    return f"{user_id}:{application_id}:{provider}".encode()


def hint_for(key: SecretStr) -> str:
    """The last characters of a key, which the researcher reads to tell keys apart."""
    return key.get_secret_value()[-_HINT_CHARS:]


@dataclass(frozen=True)
class ProviderKeyCipher:
    """Seals and opens provider keys under one server secret."""

    secret: bytes = field(repr=False)

    def seal(self, key: SecretStr, *, aad: bytes) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        sealed = AESGCM(self.secret).encrypt(
            nonce, key.get_secret_value().encode(), aad
        )
        return _SCHEME + nonce + sealed

    def open(self, blob: bytes, *, aad: bytes) -> SecretStr:
        """Raise ``cryptography.exceptions.InvalidTag`` when the blob does not open."""
        nonce = blob[len(_SCHEME) : len(_SCHEME) + _NONCE_BYTES]
        sealed = blob[len(_SCHEME) + _NONCE_BYTES :]
        return SecretStr(AESGCM(self.secret).decrypt(nonce, sealed, aad).decode())
