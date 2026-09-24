"""A stored key is sealed, listed by its tail, read only while live, and only by its owner."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator

import pytest
from assistant_core.platform.context import application_id_ctx
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.provider_keys import KeyRefusal, KeyStatuses
from pathfinder.persistence.models import UserProviderKey
from pathfinder.platform.config import get_settings
from pathfinder.services.provider_keys import (
    key_statuses,
    list_keys,
    load_keyring,
    record_refusals,
    revoke_key,
    store_key,
)
from pathfinder.tests._support.provider_keys import (
    made_up_secret,
    sealed_provider_keys,
)
from pathfinder.tests.integration.http.conftest import make_user

_SENTINEL = "sk-proj-sentinel-0123456789WXYZ"
_SECOND = "sk-proj-second-key-0123456789QRST"


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession], db_cleaner: None
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
def _sealed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with sealed_provider_keys(monkeypatch):
        yield


async def _rows(session: AsyncSession) -> list[UserProviderKey]:
    result = await session.execute(
        select(UserProviderKey).order_by(UserProviderKey.created_at)
    )
    return list(result.scalars())


@pytest.mark.usefixtures("_sealed", "patch_app_db_engine")
async def test_a_stored_key_lists_by_its_tail_and_the_row_holds_no_plaintext(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)

    view = await store_key(db_session, user.id, "openai", SecretStr(_SENTINEL))
    await db_session.commit()

    assert (view.provider, view.hint, view.status) == ("openai", "WXYZ", "active")
    assert _SENTINEL not in view.model_dump_json()
    [row] = await _rows(db_session)
    assert row.ciphertext is not None
    assert _SENTINEL.encode() not in row.ciphertext
    assert [k.hint for k in await list_keys(db_session, user.id)] == ["WXYZ"]


@pytest.mark.usefixtures("_sealed", "patch_app_db_engine")
async def test_a_second_key_revokes_the_first_and_drops_its_ciphertext(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)

    await store_key(db_session, user.id, "openai", SecretStr(_SENTINEL))
    await store_key(db_session, user.id, "openai", SecretStr(_SECOND))
    await db_session.commit()

    first, second = await _rows(db_session)
    assert (first.hint, first.revoked_at is not None, first.ciphertext) == (
        "WXYZ",
        True,
        None,
    )
    assert (second.hint, second.revoked_at, second.ciphertext is not None) == (
        "QRST",
        None,
        True,
    )
    keyring = await load_keyring(user.id)
    assert {p: k.get_secret_value() for p, k in keyring.active.items()} == {
        "openai": _SECOND
    }


@pytest.mark.usefixtures("_sealed", "patch_app_db_engine")
async def test_a_revoked_key_is_not_read(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await store_key(db_session, user.id, "anthropic", SecretStr(_SENTINEL))
    await db_session.commit()

    assert await revoke_key(db_session, user.id, "anthropic") is True
    await db_session.commit()

    keyring = await load_keyring(user.id)
    assert (dict(keyring.active), dict(keyring.refused)) == ({}, {})
    assert await list_keys(db_session, user.id) == []
    assert await revoke_key(db_session, user.id, "anthropic") is False


@pytest.mark.usefixtures("_sealed", "patch_app_db_engine")
async def test_a_revoked_row_refuses_a_ciphertext_put_back(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    await store_key(db_session, user.id, "google", SecretStr(_SENTINEL))
    await revoke_key(db_session, user.id, "google")
    await db_session.commit()

    with pytest.raises(
        IntegrityError, match="ck_user_provider_keys_live_holds_the_key"
    ):
        await db_session.execute(
            text("UPDATE user_provider_keys SET ciphertext = 'x'::bytea")
        )
    await db_session.rollback()


@pytest.mark.usefixtures("_sealed", "patch_app_db_engine")
async def test_another_user_and_another_application_never_hold_the_key(
    db_session: AsyncSession,
) -> None:
    owner = await make_user(db_session)
    stranger = await make_user(db_session)
    await store_key(db_session, owner.id, "openai", SecretStr(_SENTINEL))
    await db_session.commit()

    strangers_keyring = await load_keyring(stranger.id)
    token = application_id_ctx.set("companion")
    try:
        other_application = await load_keyring(owner.id)
    finally:
        application_id_ctx.reset(token)

    assert dict(strangers_keyring.active) == {}
    assert dict(other_application.active) == {}


@pytest.mark.usefixtures("patch_app_db_engine")
async def test_a_key_the_secret_no_longer_opens_is_marked_unreadable(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user(db_session)
    settings = get_settings()
    monkeypatch.setattr(settings, "provider_key_encryption_key", made_up_secret(7))
    await store_key(db_session, user.id, "openai", SecretStr(_SENTINEL))
    await db_session.commit()

    monkeypatch.setattr(settings, "provider_key_encryption_key", made_up_secret(9))
    keyring = await load_keyring(user.id)

    assert (dict(keyring.active), dict(keyring.refused)) == (
        {},
        {"openai": KeyRefusal.UNREADABLE},
    )
    assert await key_statuses(db_session, user.id) == KeyStatuses(
        refused={"openai": KeyRefusal.UNREADABLE}
    )


@pytest.mark.usefixtures("_sealed", "patch_app_db_engine")
async def test_a_refusal_found_in_a_turn_stands_until_the_key_is_replaced(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    await store_key(db_session, user.id, "openai", SecretStr(_SENTINEL))
    await db_session.commit()

    await record_refusals(user.id, {"openai": KeyRefusal.INVALID})

    assert await key_statuses(db_session, user.id) == KeyStatuses(
        refused={"openai": KeyRefusal.INVALID}
    )
    [view] = await list_keys(db_session, user.id)
    assert (view.status, view.refusal) == ("refused", KeyRefusal.INVALID)

    await store_key(db_session, user.id, "openai", SecretStr(_SECOND))
    await db_session.commit()
    assert await key_statuses(db_session, user.id) == KeyStatuses(
        active=frozenset({"openai"})
    )
