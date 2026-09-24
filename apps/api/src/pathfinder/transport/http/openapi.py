"""Post-passes over the generated OpenAPI schema.

Declares the RFC 9457 problem+json error contract, and anchors the models the
generated client needs but no route returns.
"""

from functools import cache
from typing import Any

from assistant_core.conversation.stream_parts.core_parts import STREAM_PARTS
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


@cache
def _stream_parts_index() -> type[BaseModel]:
    """The index model of every registered ``data-*`` payload.

    Each installed assistant registers its parts once, so the spec carries the
    union of them.
    """
    for spec in get_assistant_registry().specs():
        if spec.register_stream_parts is not None:
            spec.register_stream_parts(STREAM_PARTS)
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
