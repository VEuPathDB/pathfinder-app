from __future__ import annotations

from dataclasses import dataclass

from assistant_core.errors import ModelDeclinedError
from pydantic import BaseModel, ConfigDict
from pydantic_ai.capabilities.abstract import AbstractCapability, AgentNode, NodeResult
from pydantic_ai.exceptions import ContentFilterError
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.tools import AgentDepsT, RunContext

from pathfinder.platform.model_catalog import get_model_entry

_EXPLANATION_LIMIT = 200
_BIOLOGICAL = "bio"


class RefusalDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")

    refusal: str | None = None
    refusal_category: str | None = None

    @property
    def plain_explanation(self) -> str | None:
        text = (self.refusal or "").strip()
        if not text or len(text) > _EXPLANATION_LIMIT:
            return None
        return text if text.isascii() and text.isprintable() else None

    @property
    def filters(self) -> str:
        if self.refusal_category in {None, _BIOLOGICAL}:
            return "biological safety filters"
        return "safety filters"


def refusal_details(error: ContentFilterError) -> RefusalDetails:
    if error.body is None:
        return RefusalDetails()
    match ModelMessagesTypeAdapter.validate_json(error.body):
        case [ModelResponse(provider_details=dict() as details)]:
            return RefusalDetails.model_validate(details)
        case _:
            return RefusalDetails()


def declined_text(model_id: str, details: RefusalDetails) -> str:
    entry = get_model_entry(model_id)
    name = "The model" if entry is None else entry.name
    explanation = details.plain_explanation
    sentences = [
        f"{name} declined this request.",
        f"Its provider's {details.filters} blocked it.",
        None if explanation is None else f'The provider said: "{explanation}"',
        (
            "These filters sometimes block legitimate research questions "
            "(false positives)."
        ),
        "Try rephrasing it, or pick a different model in Settings.",
    ]
    return " ".join(sentence for sentence in sentences if sentence is not None)


@dataclass
class DeclinedRequests(AbstractCapability[AgentDepsT]):
    async def on_node_run_error(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        node: AgentNode[AgentDepsT],
        error: Exception,
    ) -> NodeResult[AgentDepsT]:
        del node
        if not isinstance(error, ContentFilterError):
            raise error
        model_id = ctx.model.model_id
        raise ModelDeclinedError(
            declined_text(model_id, refusal_details(error)), model_id=model_id
        ) from error


__all__ = ["DeclinedRequests", "RefusalDetails", "declined_text", "refusal_details"]
