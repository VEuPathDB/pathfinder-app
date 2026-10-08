"""The doubles a suite uses to state that its user is signed in to VEuPathDB."""

from collections.abc import Generator
from typing import Annotated
from uuid import UUID

import pytest
from assistant_core.registry import resolve_turn_assistant
from assistant_core.spec import AssistantSpec
from fastapi import Depends, FastAPI

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.platform.security import auth_cookie, decode_user_id, site_login_user
from pathfinder.transport.http.deps import (
    get_current_user_with_db_row,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.routers.chat import resolve_chat_assistant


@pytest.fixture
def site_login_matches_session(app: FastAPI) -> Generator[None]:
    """Let the website login of every request name the user its session names."""

    async def _session_user(
        cookie_token: Annotated[str | None, Depends(auth_cookie)] = None,
    ) -> UUID | None:
        return None if cookie_token is None else decode_user_id(cookie_token)

    app.dependency_overrides[site_login_user] = _session_user
    yield
    app.dependency_overrides.pop(site_login_user, None)


@pytest.fixture
def signed_in_to_veupathdb(
    app: FastAPI, site_login_matches_session: None
) -> Generator[None]:
    """Let the WDK-backed routes run as a user who holds a VEuPathDB session.

    The gate itself is covered by ``test_wdk_login_required``; a suite about
    what a route does once past it states that it is past it. Chat resolves
    its gate from the assistant, so that route drops the requirement instead
    of the dependency, and still routes and refuses as it does in production.
    """
    del site_login_matches_session

    async def _identity(
        user_id: Annotated[UUID, Depends(get_current_user_with_db_row)],
    ) -> UUID:
        return user_id

    async def _assistant_without_identity(body: ChatRequestBody) -> AssistantSpec:
        return await resolve_turn_assistant(
            registry=get_assistant_registry(),
            conversation_id=body.conversation_id,
            requested_id=body.assistant_id,
        )

    app.dependency_overrides[require_registered_wdk_identity] = _identity
    app.dependency_overrides[resolve_chat_assistant] = _assistant_without_identity
    yield
    app.dependency_overrides.pop(require_registered_wdk_identity, None)
    app.dependency_overrides.pop(resolve_chat_assistant, None)
