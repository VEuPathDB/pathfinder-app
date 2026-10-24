"""Every field a reply can reference has a display form, so no stored value renders raw."""

from __future__ import annotations

from collections.abc import Iterator
from typing import get_args, get_type_hints

from pydantic import BaseModel
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.audit.check_tools import build_check_toolset
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.fact_sources import FACT_SOURCES
from pathfinder.ai.audit.facts import AuditRead
from pathfinder.ai.audit.run_tools import build_run_toolset
from pathfinder.ai.audit.synthesis import SynthesisCounts
from pathfinder.domain.statistic_facts import TURN_STATISTICS, StatisticKind
from pathfinder.domain.statistic_rows import fact_schema

_HAND_BUILT: frozenset[StatisticKind] = frozenset(
    {"pca", "two_by_two", "contingency", "boxplot", "trend"}
)
_DISPLAY_KINDS = {"number", "share", "boolean", "words", "string"}


def _answers(annotation: object) -> Iterator[type[BaseModel]]:
    match annotation:
        case type() if issubclass(annotation, AuditRead):
            yield from _answers(annotation.model_fields["answer"].annotation)
        case type() if issubclass(annotation, BaseModel):
            yield annotation
        case _:
            for arg in get_args(annotation):
                yield from _answers(arg)


def _tool_answers(toolset: FunctionToolset[AuditDeps]) -> set[type[BaseModel]]:
    return {
        answer
        for tool in toolset.tools.values()
        for answer in _answers(get_type_hints(tool.function)["return"])
    }


def test_every_statistic_kind_is_hand_built_or_read_from_an_audit_answer() -> None:
    kinds = set(get_args(StatisticKind.__value__))

    assert kinds == {*_HAND_BUILT, *TURN_STATISTICS, "audit_synthesis"}
    assert _HAND_BUILT.isdisjoint(TURN_STATISTICS)


def test_the_registry_holds_every_answer_a_tool_returns_and_the_synthesis() -> None:
    read = {*_tool_answers(build_run_toolset()), *_tool_answers(build_check_toolset())}

    assert set(FACT_SOURCES) == {*read, SynthesisCounts}
    assert len(FACT_SOURCES) == len(set(FACT_SOURCES)) == 16


def test_every_field_of_every_registered_answer_has_a_display_form() -> None:
    for source in FACT_SOURCES:
        kinds = {kind for _, kind in fact_schema(source).leaves}

        assert len(kinds) >= 1, source.__name__
        assert kinds <= _DISPLAY_KINDS, source.__name__
