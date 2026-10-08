"""VEuPathDB auth request/response DTOs."""

from assistant_core.platform.pydantic_base import CamelModel


class AuthSuccessResponse(CamelModel):
    """Success response. Auth token is set via httpOnly cookie only."""

    success: bool


class AuthStatusResponse(CamelModel):
    """Current auth status response."""

    signedIn: bool
