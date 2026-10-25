"""A filter value reads as its clauses, each field by the name the recorded sheet shows."""

from __future__ import annotations

from veupathdb.domain.parameters import FilterValue
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.lead.turn_facts import _shown
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.tests._support.recorded_searches import suite_search

_SAMPLES = "variation_sample_meta"
_VALUE = FilterValue.model_validate(
    {
        "filters": [
            {"field": "VAR_68bb04bd", "type": "string", "value": ["female"]},
            {
                "field": "VAR_dc0e1a57",
                "type": "number",
                "isRange": True,
                "value": {"min": 2010, "max": 2015},
            },
            {"field": "VAR_00000000", "value": ["PfSample"], "includeUnknown": True},
        ]
    }
)


def test_each_clause_reads_with_the_field_name_the_sheet_shows() -> None:
    sheet = format_param_info_typed(
        list(suite_search("search_genes_by_ngs_snps").parameters or [])
    )

    bound = bind_values({_SAMPLES: _VALUE}, "stated", sheet)[_SAMPLES]

    assert bound.words == (
        "sex: female; Collection Year: 2010 to 2015; VAR_00000000: PfSample or unknown"
    )


def test_the_facts_row_shows_the_words_and_no_joined_label() -> None:
    sheet = format_param_info_typed(
        list(suite_search("search_genes_by_ngs_snps").parameters or [])
    )
    bound = bind_values({_SAMPLES: _VALUE}, "stated", sheet)[_SAMPLES]
    criterion = Criterion(id="c_samples", text="female samples from 2010 to 2015")

    assert _shown(criterion, _SAMPLES, bound) == (
        "sex: female; Collection Year: 2010 to 2015; VAR_00000000: PfSample or unknown",
        "",
        1,
    )
