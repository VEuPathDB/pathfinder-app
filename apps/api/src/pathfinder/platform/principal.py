"""Who a request acts as: the user, the calling application, and the credential."""

from typing import Literal
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from pathfinder.platform.identity import PATHFINDER_APPLICATION_ID

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
    application_id: str = PATHFINDER_APPLICATION_ID
    credential: CredentialKind
