"""The shared readers the EDA tools, the compute job and the tab all use."""

from __future__ import annotations

import json

from veupathdb.eda.models import (
    EdaStringSetFilter,
    EdaStudyDetail,
    EdaStudyDetailResponse,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.services.eda.description import display_names, filter_summaries

FIXTURES = FIXTURE_DIR

_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
_SPECIES = "VAR_035294d0"


def _phenotype_study() -> EdaStudyDetailResponse:
    return EdaStudyDetailResponse.model_validate(
        json.loads((FIXTURES / "study_detail_phenotype.json").read_text())
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
