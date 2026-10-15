"""VEuPathDB auth request/response DTOs."""

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field


class LoginPayload(CamelModel):
    """A VEuPathDB email and password."""

    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AuthSuccessResponse(CamelModel):
    """Success response. Auth token is set via httpOnly cookie only."""

    success: bool


class AuthStatusResponse(CamelModel):
    """Current auth status response."""

    signedIn: bool
