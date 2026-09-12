"""The ledger's sections: frame readiness, contrasts, build results, verdicts."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    FrameSection,
    VerificationSection,
)
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)


def _fold_change_criterion(
    *, comparator: str, reference: str, direction: str
) -> Criterion:
    return Criterion(
        id="female_enrichment",
        text="genes enriched in female adults",
        search_name="GenesByMicroarray_GSE22339_male_vs_female_RSRC",
        resolved_params={
            "samples_fc_comp_generic": MultiPickValue(values=[comparator]),
            "samples_fc_ref_generic": MultiPickValue(values=[reference]),
            "regulated_dir": SinglePickValue(value=direction),
            "protein_coding_only": SinglePickValue(value="yes"),
        },
    )


def _section(*criteria: Criterion) -> FrameSection:
    return FrameSection(spec=OperationalSpec(criteria=list(criteria)))


def test_contrast_reports_comparator_reference_and_direction() -> None:
    section = _section(
        _fold_change_criterion(
            comparator="female", reference="male", direction="up-regulated"
        )
    )
    contrasts = section.contrasts
    assert len(contrasts) == 1
    contrast = contrasts[0]
    assert contrast.criterion_id == "female_enrichment"
    assert contrast.comparator == "female"
    assert contrast.reference == "male"
    assert contrast.direction == "up-regulated"


def test_contrast_summary_reads_the_way_a_biologist_states_it() -> None:
    section = _section(
        _fold_change_criterion(
            comparator="female", reference="male", direction="up-regulated"
        )
    )
    assert section.contrasts[0].summary == "up-regulated in female vs male"


def test_an_inverted_contrast_reads_differently_so_it_can_be_spotted() -> None:
    inverted = _section(
        _fold_change_criterion(
            comparator="male", reference="female", direction="up-regulated"
        )
    )
    assert inverted.contrasts[0].summary == "up-regulated in male vs female"


def test_criteria_without_a_contrast_pair_are_not_reported() -> None:
    plain = Criterion(
        id="obp",
        text="odorant binding proteins",
        search_name="GenesByText",
        resolved_params={"text_expression": SinglePickValue(value="odorant binding")},
    )
    assert _section(plain).contrasts == []


def test_a_half_bound_contrast_still_surfaces_what_is_known() -> None:
    """A reference awaiting an answer must not hide the comparator."""
    half = Criterion(
        id="c",
        text="t",
        search_name="S",
        resolved_params={
            "samples_fc_comp_generic": MultiPickValue(values=["female"]),
            "regulated_dir": SinglePickValue(value="up-regulated"),
        },
    )
    contrast = _section(half).contrasts[0]
    assert contrast.comparator == "female"
    assert contrast.reference is None
    assert contrast.summary == "up-regulated in female vs (unset)"


def test_no_spec_means_no_contrasts() -> None:
    assert FrameSection().contrasts == []


def _ready_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="g",
        criteria=[Criterion(id="c1", text="x", search_name="GenesByTaxon")],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c1")),
    )


def test_frame_section_absent_when_no_spec() -> None:
    section = FrameSection(spec=None)
    assert section.present is False
    assert section.needs_user is False
    assert section.ready_to_build is False


def test_frame_section_needs_user_with_open_slot() -> None:
    spec = _ready_spec()
    spec.criteria[0].open_params = [OpenSlot(criterion_id="c1", param_name="dataset")]
    section = FrameSection(spec=spec)
    assert section.present is True
    assert section.open_slot_count == 1
    assert section.needs_user is True
    assert section.ready_to_build is False


def test_frame_section_ready_to_build_when_bound() -> None:
    section = FrameSection(spec=_ready_spec())
    assert section.bound_count == 1
    assert section.ready_to_build is True


def test_frame_section_surfaces_structure_render() -> None:
    spec = OperationalSpec(
        goal="g",
        criteria=[
            Criterion(id="c1", text="a", search_name="GenesByText"),
            Criterion(id="c2", text="b", search_name="GenesByTaxon"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c1"),
                    StructureNode(kind="leaf", criterion_id="c2"),
                ],
            )
        ),
    )
    dumped = FrameSection(spec=spec).model_dump(
        by_alias=True, mode="json", exclude_none=True
    )
    assert dumped["structureRender"] == "(GenesByText INTERSECT GenesByTaxon)"


def test_frame_section_structure_render_absent_without_structure() -> None:
    section = FrameSection(spec=OperationalSpec(goal="g"))
    dumped = section.model_dump(by_alias=True, mode="json", exclude_none=True)
    assert "structureRender" not in dumped


def test_build_section_succeeded() -> None:
    outcome = BuildOutcome(pushed_step_ids=["s1"], wdk_strategy_id=1, root_count=10)
    section = BuildSection(outcome=outcome, pushed_count=1)
    assert section.succeeded is True


def test_build_section_not_succeeded_with_failures() -> None:
    section = BuildSection(failed_count=1)
    assert section.succeeded is False


def test_build_section_defaults_to_fresh() -> None:
    section = BuildSection()
    dumped = section.model_dump(by_alias=True, mode="json", exclude_none=True)
    assert section.stale_build is None
    assert "staleBuild" not in dumped


def test_build_section_surfaces_node_results_and_strategy_link() -> None:
    outcome = BuildOutcome(
        pushed_step_ids=["s1", "s2"],
        wdk_strategy_id=42,
        wdk_url="https://plasmodb.org/s/42",
        root_count=10,
        node_results=[
            NodeResult(
                node_id="n1",
                search_name="GenesByText",
                wdk_step_id=1,
                count=10,
                status="ok",
            ),
            NodeResult(
                node_id="n2",
                search_name="GenesByOrthologs",
                count=None,
                status="failed",
                error="Answer Params must be null",
            ),
        ],
    )
    section = BuildSection(outcome=outcome, pushed_count=2)
    dumped = section.model_dump(by_alias=True, mode="json", exclude_none=True)
    assert dumped["wdkStrategyId"] == 42
    assert dumped["wdkUrl"] == "https://plasmodb.org/s/42"
    assert [n["searchName"] for n in dumped["nodeResults"]] == [
        "GenesByText",
        "GenesByOrthologs",
    ]
    assert dumped["nodeResults"][1]["status"] == "failed"
    assert dumped["nodeResults"][1]["error"] == "Answer Params must be null"


def test_build_section_node_results_empty_without_outcome() -> None:
    dumped = BuildSection().model_dump(by_alias=True, mode="json", exclude_none=True)
    assert dumped["nodeResults"] == []
    assert "wdkStrategyId" not in dumped


def test_verification_section_successful_only_when_digest_success() -> None:
    digest_ok = VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="ok",
        reason="x",
        success=True,
    )
    section_ok = VerificationSection(digest=digest_ok)
    assert section_ok.successful is True
    section_pending = VerificationSection()
    assert section_pending.successful is False
