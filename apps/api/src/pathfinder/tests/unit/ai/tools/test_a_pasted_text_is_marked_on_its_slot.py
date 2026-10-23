from __future__ import annotations

from veupathdb.domain.parameters import UnboundParameter
from veupathdb.wdk import WDKSearch, WDKStringParam

from pathfinder.ai.tools.standalone._frame_sources import open_slots, pasted_params
from pathfinder.tests.unit.ai.tools.test_frame_spec import param_info

_SEARCH = WDKSearch.model_validate(
    {
        "url_segment": "AnySequenceSearch",
        "parameters": [
            WDKStringParam(name="query_sequence", is_multi_line=True),
            WDKStringParam(name="query_label"),
        ],
    }
)


def test_a_multi_line_text_is_pasted_and_a_line_is_not() -> None:
    slots = open_slots(
        "c_seq",
        [
            UnboundParameter(param_name="query_sequence"),
            UnboundParameter(param_name="query_label"),
        ],
        [param_info("query_sequence"), param_info("query_label")],
        pasted_params(_SEARCH),
    )

    assert [(s.param_name, s.pasted) for s in slots] == [
        ("query_sequence", True),
        ("query_label", False),
    ]
