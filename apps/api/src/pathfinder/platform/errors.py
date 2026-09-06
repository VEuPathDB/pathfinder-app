"""Typed error model with problem+json responses."""

from enum import StrEnum

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

    # VEuPathDB
    SITE_NOT_FOUND = "SITE_NOT_FOUND"
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
    FORK_REFUSED = "FORK_REFUSED"
    ASSISTANT_NOT_FOUND = "ASSISTANT_NOT_FOUND"
    ASSISTANT_MISMATCH = "ASSISTANT_MISMATCH"

    # EDA
    EDA_NO_OPEN_ANALYSIS = "EDA_NO_OPEN_ANALYSIS"
    EDA_COMPUTE_NOT_RUN = "EDA_COMPUTE_NOT_RUN"

    # Specialists / launchers
    SPECIALIST_PRECONDITION_FAILED = "SPECIALIST_PRECONDITION_FAILED"
    SESSION_CONFLICT = "SESSION_CONFLICT"


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details response."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: ErrorCode
    errors: JSONArray | None = None


class AppError(Exception):
    """Base application error."""

    def __init__(
        self,
        code: ErrorCode,
        title: str,
        status: int = 400,
        detail: str | None = None,
        errors: JSONArray | None = None,
    ) -> None:
        self.code = code
        self.title = title
        self.status = status
        self.detail = detail
        self.errors = errors
        msg = f"{title}: {detail}" if detail else title
        super().__init__(msg)


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


_GENERIC_ERROR = "An internal error occurred"


def sanitize_error_for_client(exc: BaseException) -> str:
    """Return a user-safe error message.

    Only an ``AppError`` carries a user-facing title and detail. Every other
    exception gets a generic message.
    """
    if isinstance(exc, (AppError, VEuPathDBError)):
        return str(exc)
    return _GENERIC_ERROR
