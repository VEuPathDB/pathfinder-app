"""The doubles a suite uses to state that its user is signed in to VEuPathDB."""

from collections.abc import Generator
from typing import Annotated
from uuid import UUID

import pytest
from assistant_core.registry import resolve_turn_assistant
from assistant_core.spec import AssistantSpec
from fastapi import Depends, FastAPI, Request

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.platform.security import decode_user_id, site_login_user
from pathfinder.transport.http.deps import (
    get_current_user_with_db_row,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.routers.chat import resolve_chat_assistant

# The cookie a test client signs in with, as a website login does. Its value is
# a PathFinder token naming the user, read in place of VEuPathDB's account lookup.
SITE_LOGIN_COOKIE = "Authorization"


@pytest.fixture
def site_login_names_the_user(app: FastAPI) -> Generator[None]:
    """Let the website login of every request name the user its token names."""

    async def _site_user(request: Request) -> UUID | None:
        token = request.cookies.get(SITE_LOGIN_COOKIE)
        return None if token is None else decode_user_id(token)

    app.dependency_overrides[site_login_user] = _site_user
    yield
    app.dependency_overrides.pop(site_login_user, None)


@pytest.fixture
def signed_in_to_veupathdb(
    app: FastAPI, site_login_names_the_user: None
) -> Generator[None]:
    """Let the WDK-backed routes run as a user who holds a VEuPathDB session.

    The gate itself is covered by ``test_wdk_login_required``; a suite about
    what a route does once past it states that it is past it. Chat resolves
    its gate from the assistant, so that route drops the requirement instead
    of the dependency, and still routes and refuses as it does in production.
    """
    del site_login_names_the_user

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
