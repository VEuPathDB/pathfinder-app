"""Typed error model with problem+json responses."""

from enum import StrEnum

import httpx
from assistant_core.platform.types import JSONArray
from pydantic import BaseModel
from veupathdb.errors import VEuPathDBError


class ErrorCode(StrEnum):
    """Application error codes."""

    # General
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

    # VEuPathDB
    SITE_NOT_FOUND = "SITE_NOT_FOUND"
    SITE_UNAVAILABLE = "SITE_UNAVAILABLE"
    SEARCH_NOT_FOUND = "SEARCH_NOT_FOUND"
    INVALID_PARAMETERS = "INVALID_PARAMETERS"
    WDK_ERROR = "WDK_ERROR"
    WDK_LOGIN_REQUIRED = "WDK_LOGIN_REQUIRED"
    WDK_IDENTITY_MISMATCH = "WDK_IDENTITY_MISMATCH"

    # Strategy
    STRATEGY_NOT_FOUND = "STRATEGY_NOT_FOUND"
    STRATEGY_AST_CORRUPT = "STRATEGY_AST_CORRUPT"
    INVALID_STRATEGY = "INVALID_STRATEGY"
    STEP_NOT_FOUND = "STEP_NOT_FOUND"
    INCOMPATIBLE_STEPS = "INCOMPATIBLE_STEPS"
    ENSURE_SINGLE_OUTPUT_FAILED = "ENSURE_SINGLE_OUTPUT_FAILED"

    # Compilation / data processing
    STRATEGY_COMPILATION_ERROR = "STRATEGY_COMPILATION_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    DATA_PARSING_ERROR = "DATA_PARSING_ERROR"

    # Conversation
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
    CONVERSATION_FROM_EARLIER_BUILD = "CONVERSATION_FROM_EARLIER_BUILD"
    FORK_REFUSED = "FORK_REFUSED"
    ASSISTANT_NOT_FOUND = "ASSISTANT_NOT_FOUND"
    ASSISTANT_MISMATCH = "ASSISTANT_MISMATCH"

    # EDA
    EDA_NO_OPEN_ANALYSIS = "EDA_NO_OPEN_ANALYSIS"
    EDA_COMPUTE_NOT_RUN = "EDA_COMPUTE_NOT_RUN"

    # Specialists / launchers
    SPECIALIST_PRECONDITION_FAILED = "SPECIALIST_PRECONDITION_FAILED"
    SESSION_CONFLICT = "SESSION_CONFLICT"

    # A researcher's provider keys
    PROVIDER_KEY_REFUSED = "PROVIDER_KEY_REFUSED"
    PROVIDER_KEY_UNREADABLE = "PROVIDER_KEY_UNREADABLE"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    PROVIDER_UNREACHABLE = "PROVIDER_UNREACHABLE"
    PROVIDER_KEYS_DISABLED = "PROVIDER_KEYS_DISABLED"


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details response."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: ErrorCode
    errors: JSONArray | None = None


class AppError(VEuPathDBError[ErrorCode]):
    """Base application error. A refusal this application names the code of."""


class InternalError(AppError):
    """Internal server error (unexpected invariant failure)."""

    def __init__(
        self,
        title: str = "Internal error",
        detail: str | None = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            title=title,
            status=500,
            detail=detail,
        )


class NotFoundError(AppError):
    """Resource not found error."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.NOT_FOUND,
        title: str = "Resource not found",
        detail: str | None = None,
    ) -> None:
        super().__init__(code=code, title=title, status=404, detail=detail)


class UnauthorizedError(AppError):
    """Unauthorized error."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.UNAUTHORIZED,
        title: str = "Unauthorized",
        detail: str | None = None,
    ) -> None:
        super().__init__(code=code, title=title, status=401, detail=detail)


class ForbiddenError(AppError):
    """Forbidden error."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.FORBIDDEN,
        title: str = "Forbidden",
        detail: str | None = None,
    ) -> None:
        super().__init__(code=code, title=title, status=403, detail=detail)


class ScreeningUnavailableError(AppError):
    """The injection judge did not answer, so the message was never screened.

    The boundary fails closed: an unscreened message does not reach an agent.
    The refusal names neither the judge nor the provider behind it.
    """

    def __init__(self) -> None:
        super().__init__(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            title="Screening is unavailable",
            status=503,
            detail="Screening is unavailable. Send the message again in a moment.",
        )


class StrategyAstCorruptError(AppError):
    """A stored strategy AST does not parse, so the thread's graph is unreadable.

    Rebuilding the thread from an empty graph would overwrite the researcher's
    steps, so the read stops here instead.
    """

    def __init__(self, conversation_id: str, reasons: str) -> None:
        super().__init__(
            code=ErrorCode.STRATEGY_AST_CORRUPT,
            title="Stored strategy is unreadable",
            status=500,
            detail=(
                f"conversation {conversation_id} holds a strategy_ast that "
                f"does not parse: {reasons}"
            ),
        )


class ConversationFromEarlierBuildError(AppError):
    """A saved conversation this build cannot rebuild.

    The state a conversation keeps between turns is rebuilt by the build that
    resumes it; a value whose shape this build no longer reads ends the turn
    with a sentence the researcher can act on.
    """

    def __init__(self, conversation_id: str, reasons: str) -> None:
        super().__init__(
            code=ErrorCode.CONVERSATION_FROM_EARLIER_BUILD,
            title="This conversation cannot be continued",
            status=409,
            detail=(
                "This conversation was saved by an earlier version of "
                "PathFinder and cannot be continued. Start a new conversation; "
                f"the strategy and gene sets it built are still yours. "
                f"(conversation {conversation_id}: {reasons})"
            ),
        )


# A site notice prints these, so they are sentences and not class names. The
# order is narrowest first: a timeout is also a transport error.
SITE_DID_NOT_ANSWER = "the site did not answer"
_SITE_FAILURES: tuple[tuple[type[BaseException], str], ...] = (
    (TimeoutError, "the site did not answer in time"),
    (httpx.TimeoutException, "the site did not answer in time"),
    (VEuPathDBError, "the site answered with an error"),
    (httpx.HTTPStatusError, "the site answered with an error"),
    (OSError, "the site could not be reached"),
    (httpx.TransportError, "the site could not be reached"),
)


def site_failure_reason(
    error: BaseException, *, fallback: str = SITE_DID_NOT_ANSWER
) -> str:
    """Say why a site did not answer, for the person who reads it."""
    return next(
        (reason for kind, reason in _SITE_FAILURES if isinstance(error, kind)),
        fallback,
    )


class SiteUnavailableError(AppError):
    """A VEuPathDB site this process cannot reach.

    Raised for a catalog that did not load and for a call the site did not
    answer, so the request is refused instead of waiting out the site's own
    timeout.
    """

    def __init__(self, site_id: str, reason: str | None) -> None:
        cause = reason or "still loading"
        super().__init__(
            code=ErrorCode.SITE_UNAVAILABLE,
            title="Cannot reach the site",
            status=503,
            detail=f"Could not connect to {site_id} ({cause}).",
        )


class WDKIdentityMismatchError(AppError):
    """The VEuPathDB token names another account than the session does.

    The two credentials are independent, so a second sign-in would otherwise
    write analyses and strategies under an account the session cannot read.
    """

    def __init__(self) -> None:
        super().__init__(
            code=ErrorCode.WDK_IDENTITY_MISMATCH,
            title="VEuPathDB account changed",
            status=401,
            detail=(
                "Signed in to VEuPathDB as a different account than this "
                "PathFinder session. Sign in again."
            ),
        )


class AssistantNotFoundError(AppError):
    """A request names an assistant this deployment does not serve."""

    def __init__(self, assistant_id: str, known: tuple[str, ...]) -> None:
        super().__init__(
            code=ErrorCode.ASSISTANT_NOT_FOUND,
            title="Assistant not found",
            status=404,
            detail=(
                f"No assistant {assistant_id!r} is installed. "
                f"Installed: {', '.join(known)}."
            ),
        )


class AssistantMismatchError(AppError):
    """A request names a different assistant than the conversation was created with.

    A thread keeps one assistant for its whole life, so the caller is acting
    on a conversation it does not know the shape of.
    """

    def __init__(self, *, requested: str, existing: str) -> None:
        super().__init__(
            code=ErrorCode.ASSISTANT_MISMATCH,
            title="Assistant mismatch",
            status=409,
            detail=(
                f"This conversation is answered by {existing!r}; "
                f"the request names {requested!r}."
            ),
        )


class ForkRefusedError(AppError):
    """A branch point the new thread cannot be given."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            code=ErrorCode.FORK_REFUSED,
            title="Cannot branch this chat",
            status=409,
            detail=reason,
        )


class StrategyCompilationError(AppError):
    """Strategy compilation, step creation, or step-tree assembly failure."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            code=ErrorCode.STRATEGY_COMPILATION_ERROR,
            title="Strategy compilation failed",
            status=500,
            detail=detail,
        )


_KEYS_IN_SETTINGS = "Settings, under Provider keys"


class ProviderKeyError(AppError):
    """No key may pay for a model the request names.

    Other call arguments cannot pass it, so a model is never asked to retry.
    """


class ProviderKeyRefusedError(ProviderKeyError):
    """The provider refused the researcher's key, so nothing may run on it.

    Nothing falls back to the deployment's key.
    """

    def __init__(self, provider_name: str, *, status: int = 409) -> None:
        super().__init__(
            code=ErrorCode.PROVIDER_KEY_REFUSED,
            title=f"{provider_name} refused your key",
            status=status,
            detail=(
                f"{provider_name} refused the key you added, so nothing ran on it. "
                f"Replace or remove your {provider_name} key in {_KEYS_IN_SETTINGS}."
            ),
        )


class ProviderKeyUnreadableError(ProviderKeyError):
    """The server secret no longer opens the researcher's stored key."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(
            code=ErrorCode.PROVIDER_KEY_UNREADABLE,
            title=f"Your {provider_name} key cannot be read",
            status=409,
            detail=(
                f"This server can no longer read the {provider_name} key you "
                f"added, so nothing ran on it. Enter the key again in "
                f"{_KEYS_IN_SETTINGS}."
            ),
        )


class ProviderNotConfiguredError(ProviderKeyError):
    """Neither the researcher nor the deployment holds a key for the provider."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(
            code=ErrorCode.PROVIDER_NOT_CONFIGURED,
            title=f"No {provider_name} key",
            status=422,
            detail=(
                f"This deployment holds no {provider_name} key and you have not "
                f"added one. Add yours in {_KEYS_IN_SETTINGS}, or choose a model "
                f"of another provider."
            ),
        )


class ProviderUnreachableError(AppError):
    """The provider did not answer the check of a new key, so it was not stored."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(
            code=ErrorCode.PROVIDER_UNREACHABLE,
            title=f"{provider_name} did not answer",
            status=503,
            detail=(
                f"{provider_name} did not answer the check of your key, so it was "
                "not saved. Try again in a moment."
            ),
        )


class ProviderKeysDisabledError(AppError):
    """The deployment holds no secret to seal a researcher's key under.

    The refusal stands until an operator sets the secret, so it is a 403 and
    not an outage a caller may wait out.
    """

    def __init__(self) -> None:
        super().__init__(
            code=ErrorCode.PROVIDER_KEYS_DISABLED,
            title="Personal keys are off",
            status=403,
            detail="This deployment does not accept personal provider keys.",
        )


_GENERIC_ERROR = "An internal error occurred"


def sanitize_error_for_client(exc: BaseException) -> str:
    """Return a user-safe error message.

    Only a refusal carries a user-facing title and detail. Every other
    exception gets a generic message.
    """
    if isinstance(exc, VEuPathDBError):
        return str(exc)
    return _GENERIC_ERROR
