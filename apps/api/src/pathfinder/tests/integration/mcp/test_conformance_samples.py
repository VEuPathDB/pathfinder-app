from __future__ import annotations

import inspect

from pydantic import TypeAdapter
from veupathdb_mcp.catalog import AllOf, PhyleticPattern
from veupathdb_mcp.server import TOOLS

from pathfinder.tests.integration.mcp._served import OwnedStep
from pathfinder.tests.integration.mcp.test_conformance_ours import (
    ONLY_IN_CLADE,
    sample_arguments,
)

_SAMPLES = sample_arguments(OwnedStep(strategy_id=1, step_id=2), ["PF3D7_1133400"])


def test_every_sample_names_a_served_tool() -> None:
    served = {row.fn.__name__ for row in TOOLS}

    assert sorted(set(_SAMPLES) - served) == []
    assert len(_SAMPLES) == 17


def test_every_sample_passes_only_the_arguments_its_tool_takes() -> None:
    served = {row.fn.__name__: row.fn for row in TOOLS}
    signatures = {
        name: inspect.signature(served[name]).bind(**arguments).arguments
        for name, arguments in _SAMPLES.items()
    }

    assert signatures["build_phyletic_expression"] == {
        "site_id": "orthomcl",
        "pattern": ONLY_IN_CLADE,
    }


def test_the_builder_sample_is_a_pattern_the_tool_reads() -> None:
    adapter: TypeAdapter[PhyleticPattern] = TypeAdapter(PhyleticPattern)
    pattern = adapter.validate_python(ONLY_IN_CLADE)

    assert isinstance(pattern, AllOf)
    assert len(pattern.terms) == 2
