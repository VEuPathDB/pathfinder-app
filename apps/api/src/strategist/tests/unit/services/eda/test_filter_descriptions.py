"""The shared readers the EDA tools, the compute job and the tab all use."""

from __future__ import annotations

import json

from veupathdb.eda import (
    EdaNumberRangeFilter,
    EdaStringSetFilter,
    EdaStudyDetail,
    EdaStudyDetailResponse,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from strategist.services.eda.description import display_names, filter_summaries
from strategist.tests._support.qa_recording import qa_recording

FIXTURES = FIXTURE_DIR

_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
_SPECIES = "VAR_035294d0"


def _phenotype_study() -> EdaStudyDetailResponse:
    return EdaStudyDetailResponse.model_validate(
        json.loads(qa_recording(FIXTURES / "study_detail_phenotype.json").read_text())
    )


def _two_level_study() -> EdaStudyDetail:
    return EdaStudyDetail.model_validate(
        {
            "id": "STUDY_two_level",
            "rootEntity": {
                "id": "PARENT",
                "displayName": "Participant",
                "variables": [
                    {"id": "VAR_p", "type": "string", "displayName": "Country"}
                ],
                "children": [
                    {
                        "id": "CHILD",
                        "displayName": "Sample",
                        "variables": [
                            {
                                "id": "VAR_c",
                                "type": "string",
                                "displayName": "Tissue",
                            }
                        ],
                    }
                ],
            },
        }
    )


def test_display_names_keys_a_variable_by_its_entity_and_its_id() -> None:
    names = display_names(_phenotype_study().study)
    assert names[(_ENTITY, _SPECIES)] == "Species"


def test_display_names_reaches_a_variable_on_a_child_entity() -> None:
    """A study is a tree, so a root-only read loses every child's variable."""
    names = display_names(_two_level_study())
    assert names == {
        ("PARENT", "VAR_p"): "Country",
        ("CHILD", "VAR_c"): "Tissue",
    }


def test_filter_summaries_reads_the_name_display_names_supplies() -> None:
    """The two helpers are used together, so the key shapes must agree."""
    summaries = filter_summaries(
        [
            EdaStringSetFilter(
                entity_id=_ENTITY,
                variable_id=_SPECIES,
                string_set=["P. berghei"],
            )
        ],
        display_names=display_names(_phenotype_study().study),
    )
    assert summaries == ["Species is one of P. berghei"]


def test_a_range_with_equal_ends_reads_as_the_one_value_it_keeps() -> None:
    summaries = filter_summaries(
        [
            EdaNumberRangeFilter(
                entity_id=_ENTITY, variable_id="VAR_rank", min=1.0, max=1.0
            ),
            EdaNumberRangeFilter(
                entity_id=_ENTITY, variable_id="VAR_score", min=-6.9, max=-3.0
            ),
        ],
        display_names={
            (_ENTITY, "VAR_rank"): "Phenotype Rank",
            (_ENTITY, "VAR_score"): "Mean Phenotype Score",
        },
    )
    assert summaries == [
        (
            "Phenotype Rank is exactly 1.0: both ends of the range are equal, so "
            "no other value passes"
        ),
        "Mean Phenotype Score is between -6.9 and -3.0",
    ]
