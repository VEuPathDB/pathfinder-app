from __future__ import annotations

import inspect

from veupathdb_mcp.server import TOOLS

from pathfinder.tests._support.orthomcl_counts import CRYPTOSPORIDIUM
from pathfinder.tests.integration.mcp._served import OwnedStep
from pathfinder.tests.integration.mcp.test_conformance_ours import sample_arguments

_SAMPLES = sample_arguments(OwnedStep(strategy_id=1, step_id=2), ["PF3D7_1133400"])


def test_every_sample_names_a_served_tool() -> None:
    served = {row.fn.__name__ for row in TOOLS}

    assert sorted(set(_SAMPLES) - served) == []
    assert len(_SAMPLES) == 19


def test_every_sample_passes_only_the_arguments_its_tool_takes() -> None:
    served = {row.fn.__name__: row.fn for row in TOOLS}
    signatures = {
        name: inspect.signature(served[name]).bind(**arguments).arguments
        for name, arguments in _SAMPLES.items()
    }

    assert signatures["build_protein_count_comparison"] == {
        "site_id": "orthomcl",
        "genome_a": "tgon",
        "genome_b": "pfal",
        "reverse": True,
    }
    assert signatures["build_clade_only_expression"] == {
        "site_id": "orthomcl",
        "clade": ["APIC"],
    }
    assert signatures["build_every_species_expression"] == {
        "site_id": "orthomcl",
        "clade": CRYPTOSPORIDIUM,
    }
