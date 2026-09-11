"""The snapshot is a projection of the library's parameter model."""

from __future__ import annotations

from veupathdb.domain.parameters.wdk_vocab import VocabOption
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import ParamVocabSnapshot


def _info() -> ParameterInfo:
    return ParameterInfo(
        name="hard_floor",
        display_name="Tier floor",
        type="number-enum",
        required=True,
        is_visible=True,
        help="Tier-quantile floor for read counts",
        value_format="single",
        default_value="6772.93",
        allowed_values=[
            VocabOption(value="1693.23", display="1693 reads"),
            VocabOption(value="6772.93", display="6772 reads"),
        ],
    )


def test_the_snapshot_reads_the_library_parameter() -> None:
    snapshot = ParamVocabSnapshot.model_validate(_info(), from_attributes=True)

    assert snapshot.param_type == "number-enum"
    assert snapshot.required is True
    assert snapshot.help == "Tier-quantile floor for read counts"
    assert snapshot.default_value == "6772.93"
    assert snapshot.allowed_values == [
        VocabOption(value="1693.23", display="1693 reads"),
        VocabOption(value="6772.93", display="6772 reads"),
    ]
    assert snapshot.allowed_values_tree is None


def test_the_snapshot_still_takes_its_own_field_name() -> None:
    """The prompts read ``param_type``, so the alias keeps both names."""
    snapshot = ParamVocabSnapshot(param_type="string", required=False)

    assert snapshot.param_type == "string"
