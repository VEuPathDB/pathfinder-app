"""The backend half of the shared phyletic conformance fixture."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, Field, model_validator
from veupathdb.domain.parameters.phyletic import (
    PhyleticBinding,
    PhyleticTree,
    PhyleticUnresolved,
    TriState,
    derive_binding,
    read_census,
)
from veupathdb.domain.parameters.wdk_vocab import WDKVocabTerm

CONFORMANCE_FIXTURE = (
    Path(__file__).resolve().parents[6]
    / "packages"
    / "spec"
    / "phyletic_conformance.json"
)


class UnresolvedExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    included_unknown: list[str] = Field(default_factory=list)
    excluded_unknown: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class ConformanceCase(BaseModel):
    """One selection and the binding both encoders must produce for it."""

    model_config = ConfigDict(extra="forbid")

    name: str
    included: list[str]
    excluded: list[str]
    profile_pattern: str | None = None
    included_species: str | None = None
    excluded_species: str | None = None
    leaf_states: dict[str, TriState] | None = None
    unresolved: UnresolvedExpectation | None = None
    ts_skip: bool = Field(default=False, alias="tsSkip")
    ts_skip_reason: str | None = Field(default=None, alias="tsSkipReason")

    @model_validator(mode="after")
    def _skip_states_its_reason(self) -> ConformanceCase:
        if self.ts_skip != bool(self.ts_skip_reason):
            message = f"{self.name}: tsSkip and tsSkipReason must be set together"
            raise ValueError(message)
        return self


class DecodeCase(BaseModel):
    """One pattern and the two readings of it.

    ``census`` is what the wire guard reads and ``widget`` is what the editor
    reads. The frontend suite asserts the other field.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    pattern: str
    census: dict[str, TriState] | None
    widget: dict[str, TriState]
    note: str | None = None


class ConformanceFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc: str = Field(alias="_doc")
    term_map: list[tuple[str, str]]
    term_map_doc: str = Field(alias="_term_map_doc")
    indent_map: list[tuple[str, str]]
    indent_map_doc: str = Field(alias="_indent_map_doc")
    cases: list[ConformanceCase]
    decode: list[DecodeCase]


FIXTURE = ConformanceFixture.model_validate_json(CONFORMANCE_FIXTURE.read_text())


def _tree() -> PhyleticTree:
    return PhyleticTree.from_vocab(
        [WDKVocabTerm((code, label, None)) for code, label in FIXTURE.term_map],
        [WDKVocabTerm((code, depth, None)) for code, depth in FIXTURE.indent_map],
    )


@pytest.mark.parametrize("case", FIXTURE.cases, ids=lambda case: case.name)
def test_conformance_case(case: ConformanceCase) -> None:
    tree = _tree()
    binding = derive_binding(tree, case.included, case.excluded)

    if case.leaf_states is not None:
        included = tree.resolve_terms(case.included).codes
        excluded = tree.resolve_terms(case.excluded).codes
        assert tree.leaf_states(included, excluded) == case.leaf_states

    if case.unresolved is not None:
        assert isinstance(binding, PhyleticUnresolved)
        assert binding.included_unknown == case.unresolved.included_unknown
        assert binding.excluded_unknown == case.unresolved.excluded_unknown
        assert binding.conflicts == case.unresolved.conflicts
        return

    assert isinstance(binding, PhyleticBinding)
    assert binding.profile_pattern == case.profile_pattern
    assert binding.included_species == case.included_species
    assert binding.excluded_species == case.excluded_species


@pytest.mark.parametrize("case", FIXTURE.decode, ids=lambda case: case.name)
def test_decode_case(case: DecodeCase) -> None:
    assert read_census(case.pattern).states == case.census
