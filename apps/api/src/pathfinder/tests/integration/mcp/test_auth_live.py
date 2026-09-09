"""A real VEuPathDB bearer, verified the way veupathdb-wdk-mcp verifies it."""

from __future__ import annotations

import pytest
from veupathdb.wdk.current_user import fetch_current_user
from veupathdb_mcp.auth import CredentialMode, VEuPathDBTokenVerifier, wdk_identity

pytestmark = pytest.mark.live_wdk


async def test_a_registered_bearer_resolves_to_a_usable_identity(
    require_wdk_creds: str,
) -> None:
    credential = await VEuPathDBTokenVerifier().verify_token(require_wdk_creds)

    assert credential is not None
    assert credential.mode is CredentialMode.VEUPATHDB_USER
    assert credential.client_id

    with wdk_identity(credential):
        user = await fetch_current_user("plasmodb")

    assert user is not None
    assert not user.is_guest


async def test_a_forged_bearer_verifies_as_nothing(require_wdk_creds: str) -> None:
    """The signature is checked against the OAuth server's published key."""
    del require_wdk_creds

    forged = "eyJhbGciOiJFUzUxMiJ9.eyJzdWIiOiIxIiwiZXhwIjo0MTAyNDQ0ODAwfQ.bm90LWEtc2ln"

    assert await VEuPathDBTokenVerifier().verify_token(forged) is None
