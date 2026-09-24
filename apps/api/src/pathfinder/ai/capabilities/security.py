"""Host wiring for the runtime's injection judge: one judge, two boundaries.

A judgement is a model call, so it can fail. The researcher's message fails
closed, with a 503 the frontend can render; a tool result the judge could not
read is withheld on its own, so the turn that ran the tool survives.
"""

from __future__ import annotations

from functools import lru_cache
from time import perf_counter

from assistant_core.capabilities.injection_judge import ModelInjectionJudge
from assistant_core.capabilities.input_screening import (
    ScreeningRejectionError,
    UserInputScanner,
)
from assistant_core.capabilities.tool_result_screen import screened_output
from assistant_core.mcp.untrusted import OutputScan, ScanVerdict, pass_through_scan
from assistant_core.models.scripted import last_user_text, terminal_call
from assistant_core.platform.logging import get_logger
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ForbiddenError, ScreeningUnavailableError
from pathfinder.platform.model_keys import deployment_model

logger = get_logger(__name__)

_SCREENING_CONTEXT = """
This product helps a pathogen researcher build and read VEuPathDB search
strategies. A normal message is a short imperative about that work: delete a
step, clear the strategy, export the result, remember this, forget that, stop,
undo, start over, rerun it. A normal message is also a pasted list of gene
identifiers, or a question about an organism, a search, a parameter or a
count. Researchers write bluntly, and they paste papers, error text and tool
output. An off-topic request, however far from this work, is benign for this
check: another part of the product decides what to do with it.
""".strip()

# The one text the scripted judge calls an injection. A mock run reaches no
# provider, and no ordinary fixture is refused by accident.
INJECTION_TEST_MARKER = "[[pathfinder-injection-test]]"

UNSCREENED = (
    "A result from this tool was not passed on because it could not be screened."
)

_REJECTION_TITLE = "Input rejected by security screening"
_REJECTION_DETAIL = "This message was refused by prompt-injection screening. Rewrite it and send it again."


def _scripted_judge_model() -> FunctionModel:
    """The model the judge runs on under the mock provider."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        injected = INJECTION_TEST_MARKER in last_user_text(messages)
        return ModelResponse(
            parts=[terminal_call({"injection": injected, "confidence": 1.0})],
        )

    return FunctionModel(respond, model_name="mock:injection-judge")


def _judge_model() -> Model:
    """The judge always runs on the deployment's key, and its errors carry no body."""
    settings = get_settings()
    if settings.pathfinder_chat_provider.strip().lower() == "mock":
        return _scripted_judge_model()
    return deployment_model(settings.input_screening_model)


@lru_cache(maxsize=1)
def _judge() -> ModelInjectionJudge:
    return ModelInjectionJudge(_judge_model(), context=_SCREENING_CONTEXT)


@lru_cache(maxsize=1)
def _scanner() -> UserInputScanner:
    return UserInputScanner(judge=_judge())


@lru_cache(maxsize=1)
def _screened_tool_output() -> OutputScan:
    return screened_output(_judge())


def _judged(started: float, chars: int) -> None:
    logger.debug(
        "Judged one text",
        chars=chars,
        seconds=round(perf_counter() - started, 3),
    )


def warm_up_screening() -> None:
    """Build the judge the request path calls.

    A model this deployment cannot reach raises here, so readiness reports it
    before a researcher sends a message.
    """
    _judge()


def tool_output_scan() -> OutputScan:
    """The scan one turn installs on the results of its tool sources."""
    if not get_settings().input_screening_enabled:
        return pass_through_scan
    screen = _screened_tool_output()

    async def scan(text: str) -> ScanVerdict:
        started = perf_counter()
        try:
            verdict = await screen(text)
        except Exception:
            logger.exception("The judge did not answer; the result is withheld")
            return ScanVerdict(text=UNSCREENED)
        _judged(started, len(text))
        return verdict

    return scan


async def scan_user_input(text: str) -> None:
    """Screen one user message, or refuse the request.

    A judged injection is a 403. A judgement that did not happen is a 503: an
    unscreened message does not reach an agent.
    """
    if not get_settings().input_screening_enabled:
        return
    started = perf_counter()
    try:
        await _scanner().scan(text)
    except ScreeningRejectionError as refused:
        raise ForbiddenError(
            title=_REJECTION_TITLE,
            detail=_REJECTION_DETAIL,
        ) from refused
    except Exception as unavailable:
        raise ScreeningUnavailableError from unavailable
    _judged(started, len(text))


__all__ = [
    "INJECTION_TEST_MARKER",
    "UNSCREENED",
    "scan_user_input",
    "tool_output_scan",
    "warm_up_screening",
]
