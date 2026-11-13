from __future__ import annotations

from pydantic import ValidationError, ValidationInfo, ValidatorFunctionWrapHandler

from pathfinder.platform.errors import ConversationFromEarlierBuildError


def read_by_this_build(
    value: object, handler: ValidatorFunctionWrapHandler, info: ValidationInfo
) -> object:
    try:
        return handler(value)
    except ValidationError as exc:
        raise ConversationFromEarlierBuildError.of(
            str(info.data.get("conversation_id", "")), exc
        ) from exc
