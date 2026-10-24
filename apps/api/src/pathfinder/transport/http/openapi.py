"""Post-passes over the generated OpenAPI schema.

Declares the RFC 9457 problem+json error contract, and anchors the models the
generated client needs but no route returns.
"""

from collections.abc import Iterable
from functools import cache
from typing import Any

from assistant_core.conversation.stream_parts.core_parts import STREAM_PARTS
from assistant_core.conversation.stream_parts.registry import StreamPartRegistry
from assistant_core.spec import AssistantSpec
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from veupathdb.eda import EdaNewAnalysis

from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.platform.errors import ProblemDetail

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")
_PROBLEM_JSON = "application/problem+json"
_PROBLEM_SCHEMA_REF = "#/components/schemas/ProblemDetail"
_SCHEMA_REF_TEMPLATE = "#/components/schemas/{model}"


def _problem_components() -> dict[str, Any]:
    """ProblemDetail's JSON schema plus the enums it references (e.g. ErrorCode)."""
    schema = ProblemDetail.model_json_schema(ref_template=_SCHEMA_REF_TEMPLATE)
    nested = schema.pop("$defs", {})
    for prop in schema["properties"].values():
        prop.pop("default", None)
    return {"ProblemDetail": schema, **nested}


def register_stream_parts_of(
    specs: Iterable[AssistantSpec], registry: StreamPartRegistry
) -> None:
    for spec in specs:
        if spec.register_stream_parts is None:
            continue
        own = StreamPartRegistry()
        spec.register_stream_parts(own)
        for entry in own.entries():
            if entry in registry.entries():
                continue
            if entry.kind is None:
                registry.register_schema_only(entry.schema_name, entry.model)
            else:
                registry.register(entry.kind, entry.model)


@cache
def _stream_parts_index() -> type[BaseModel]:
    """The index model of every registered ``data-*`` payload.

    Each installed assistant registers its parts, so the spec carries the
    union of them; a part two assistants emit is one entry.
    """
    register_stream_parts_of(get_assistant_registry().specs(), STREAM_PARTS)
    return STREAM_PARTS.schema_index_model()


def _anchor_components() -> dict[str, Any]:
    """Schemas the generated client needs that no route returns.

    The chat stream carries the ``data-*`` payloads; an EDA step's
    ``eda_analysis_spec`` parameter holds :class:`EdaNewAnalysis` as a JSON
    string. Neither is a JSON body, so the generator reaches them only here.
    """
    components: dict[str, Any] = {}
    for model in (_stream_parts_index(), EdaNewAnalysis):
        schema = model.model_json_schema(
            mode="serialization", ref_template=_SCHEMA_REF_TEMPLATE
        )
        components.update(schema.pop("$defs", {}))
        components[model.__name__] = schema
    return components


def _inject_components(schema: dict[str, Any]) -> None:
    # FastAPI encodes its own spec with exclude_none; injected schemas get the same treatment.
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for source in (_problem_components(), _anchor_components()):
        for name, model_schema in source.items():
            components.setdefault(
                name, jsonable_encoder(model_schema, exclude_none=True)
            )


def _problem_content() -> dict[str, Any]:
    return {_PROBLEM_JSON: {"schema": {"$ref": _PROBLEM_SCHEMA_REF}}}


def _inject_problem_responses(schema: dict[str, Any]) -> None:
    for path, path_item in schema["paths"].items():
        has_path_param = "{" in path
        for method in _HTTP_METHODS:
            operation = path_item.get(method)
            if operation is None:
                continue
            responses = operation["responses"]
            if "422" in responses:
                responses["422"].setdefault("content", {}).update(_problem_content())
            if has_path_param:
                responses.setdefault(
                    "404", {"description": "Not Found", "content": _problem_content()}
                )


def install_openapi_post_passes(app: FastAPI) -> None:
    # app.openapi() builds and caches the schema; mutate the cached object.
    schema = app.openapi()
    _inject_components(schema)
    _inject_problem_responses(schema)
