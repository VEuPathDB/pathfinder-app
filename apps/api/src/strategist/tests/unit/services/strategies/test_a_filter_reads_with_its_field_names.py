"""A filter value reads as its clauses, each field by the name the recorded sheet shows."""

from __future__ import annotations

from veupathdb.domain.parameters import FilterValue

from strategist.ai.lead.parameter_facts import _shown
from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.strategy.stated_source import StatedSource
from strategist.domain.strategy.value_binding import bind_values
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.recorded_searches import suite_search

_STATED = StatedSource(words="")

_SAMPLES = "variation_sample_meta"
_VALUE = FilterValue.model_validate(
    {
        "filters": [
            {
                "field": "VAR_68bb04bd",
                "type": "string",
                "isRange": False,
                "includeUnknown": False,
                "value": ["female"],
            },
            {
                "field": "VAR_dc0e1a57",
                "type": "number",
                "isRange": True,
                "includeUnknown": False,
                "value": {"min": 2010, "max": 2015},
            },
            {
                "field": "VAR_00000000",
                "type": "string",
                "isRange": False,
                "includeUnknown": True,
                "value": ["PfSample"],
            },
        ]
    }
)


def test_each_clause_reads_with_the_field_name_the_sheet_shows() -> None:
    sheet = sheet_of(list(suite_search("search_genes_by_ngs_snps").parameters or []))

    bound = bind_values({_SAMPLES: _VALUE}, _STATED, sheet)[_SAMPLES]

    assert bound.words == (
        "sex: female; Collection Year: 2010 to 2015; VAR_00000000: PfSample or unknown"
    )


def test_the_facts_row_shows_the_words_and_no_joined_label() -> None:
    sheet = sheet_of(list(suite_search("search_genes_by_ngs_snps").parameters or []))
    bound = bind_values({_SAMPLES: _VALUE}, _STATED, sheet)[_SAMPLES]
    criterion = Criterion(id="c_samples", text="female samples from 2010 to 2015")

    assert _shown(criterion, _SAMPLES, bound) == (
        "sex: female; Collection Year: 2010 to 2015; VAR_00000000: PfSample or unknown",
        "",
        1,
    )
