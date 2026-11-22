from __future__ import annotations

from veupathdb.domain.parameters import HeldValue, SinglePickValue, VocabOption
from veupathdb_mcp.catalog import ParameterInfo

from strategist.services.strategies import pick_readings

_PNA = "pnaVsPromastigote"
_AMA = "amastigoteVsPromastigote"


def _experiment() -> ParameterInfo:
    return ParameterInfo(
        name="profileset_generic",
        display_name="Experiment",
        type="single-pick-vocabulary",
        required=True,
        is_visible=True,
        site_set=False,
        help="",
        default_value=_PNA,
        allowed_values=[VocabOption(value=v, display=v) for v in (_PNA, _AMA)],
    )


def test_a_pick_held_as_a_one_term_array_is_not_counted_again() -> None:
    others = pick_readings._other_options(HeldValue(wire=f'["{_PNA}"]'), _experiment())

    assert others == [SinglePickValue(value=_AMA)]
