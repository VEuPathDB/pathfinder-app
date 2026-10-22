"""The run owner's VEuPathDB sign-in, kept sealed on the run while the run has work left."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import jwt
from assistant_core.platform.db import async_session_factory
from cryptography.exceptions import InvalidTag
from pydantic import SecretStr, ValidationError
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import VEuPathDBClaims

from pathfinder.persistence.models import AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import AppError, ErrorCode
from pathfinder.platform.provider_key_cipher import ProviderKeyCipher


class AuditsDisabledError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code=ErrorCode.AUDITS_DISABLED,
            title="Audits are off",
            status=403,
            detail=(
                "This deployment holds no secret to keep your sign-in under, so "
                "it runs no audit."
            ),
        )


def _aad(run_id: UUID, user_id: UUID) -> bytes:
    return f"audit-run:{run_id}:{user_id}".encode()


def _cipher() -> ProviderKeyCipher:
    cipher = get_settings().provider_key_cipher
    if cipher is None:
        raise AuditsDisabledError
    return cipher


def seal_sign_in(run_id: UUID, user_id: UUID, token: str) -> bytes:
    return _cipher().seal(SecretStr(token), aad=_aad(run_id, user_id))


async def _kept_sign_in(run_id: UUID, user_id: UUID) -> str | None:
    async with async_session_factory() as session:
        sealed = await AuditRepository(session).sealed_token(run_id)
    cipher = get_settings().provider_key_cipher
    if sealed is None or cipher is None:
        return None
    try:
        return cipher.open(sealed, aad=_aad(run_id, user_id)).get_secret_value()
    except InvalidTag:
        return None


@asynccontextmanager
async def signed_in_as_owner(run: AuditRunRecord) -> AsyncIterator[None]:
    reset = veupathdb_auth_token_ctx.set(await _kept_sign_in(run.id, run.user_id))
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


def sign_in_holds() -> bool:
    token = veupathdb_auth_token_ctx.get()
    if token is None:
        return False
    try:
        claims = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": True,
                "require": ["exp", "sub"],
            },
        )
        return not VEuPathDBClaims.model_validate(claims).is_guest
    except jwt.PyJWTError, ValidationError:
        return False
