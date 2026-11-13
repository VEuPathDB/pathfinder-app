"""VEuPathDB auth request/response DTOs."""

from assistant_core.platform.pydantic_base import CamelModel


class AuthStatusResponse(CamelModel):
    """Current auth status response."""

    signedIn: bool
