"""Who a request acts as: the user, the calling application, and the credential."""

from typing import Literal
from uuid import UUID

from assistant_core.platform.context import DEFAULT_APPLICATION_ID
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

CredentialKind = Literal[
    "pathfinder-cookie",
    "pathfinder-bearer",
    "veupathdb-bearer",
    "dev-login",
]

SERVICE_AUTH_HEADER = "X-PathFinder-Service-Token"


class Principal(CamelModel):
    """The identity a request is served under."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    application_id: str = DEFAULT_APPLICATION_ID
    credential: CredentialKind
