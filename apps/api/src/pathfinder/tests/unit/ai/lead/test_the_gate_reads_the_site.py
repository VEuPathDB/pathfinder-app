"""The classification gate holds a classification to the site's organisms and genes."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart, TextUIPart
from veupathdb_mcp.audit import GeneIdProblem, GeneIdRefusal, TooManyIdsError
from veupathdb_mcp.gene_lookup import GeneIdFound, GeneIdReading, GeneResult

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import classification_gate
from pathfinder.ai.lead.intent import ClassifiedIntent, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.tests._support.orthomcl_gene_class import (
    ORTHOMCL,
    held_record_types,
    orthomcl_gene_class,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.site_organisms import recorded_organisms
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

SPORE_WALL = "Encephalitozoon cuniculi GB-M1 spore wall proteins."
BSPA = "Trichomonas vaginalis G3 BspA-like proteins."
IMAGE_QUESTION = "Which genes are in this image?"
# The ids the attached table of the plasmodb flow shows.
IMAGE_IDS = ["PF3D7_0709000", "PF3D7_1133400", "PF3D7_0102600"]


class SiteReads:
    """The organism lists and id resolutions the gate asked the site for."""

    def __init__(self, genes: list[str]) -> None:
        self.genes = genes
        self.organisms: list[str] = []
        self.resolved: list[list[str]] = []
        self.several: set[str] = set()
        self.bound: int | None = None


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> SiteReads:
    """Serve each site's recorded organisms, and resolve the image's ids as genes."""
    reads = SiteReads(genes=IMAGE_IDS)

    async def _organisms(site_id: str) -> list[str]:
        reads.organisms.append(site_id)
        return recorded_organisms(site_id)

    async def _resolve(site_id: str, gene_ids: list[str]) -> list[GeneIdReading]:
        reads.resolved.append(gene_ids)
        if reads.bound is not None and len(gene_ids) > reads.bound:
            raise TooManyIdsError(len(gene_ids), reads.bound, "record reads")
        return [_reading(site_id, g, reads) for g in gene_ids]

    monkeypatch.setattr(classification_gate, "list_organisms", _organisms)
    monkeypatch.setattr(classification_gate, "read_each_gene_id", _resolve)
    return reads


def _reading(site_id: str, gene_id: str, reads: SiteReads) -> GeneIdReading:
    if gene_id in reads.several:
        return GeneIdRefusal(
            given=gene_id,
            problem=GeneIdProblem.SEVERAL_GENES,
            message=f"{gene_id} names 2 genes of {site_id}",
        )
    if gene_id.upper() in reads.genes:
        return GeneIdFound(given=gene_id, records=[GeneResult(gene_id=gene_id)])
    return GeneIdRefusal(
        given=gene_id,
        problem=GeneIdProblem.NOT_FOUND,
        message=f"{gene_id} names no gene of {site_id}",
    )


def _intent(classification: str, **fields: object) -> UserIntent:
    return UserIntent.model_validate(
        {"classification": classification, "inferredGoal": "the goal", **fields}
    )


def _with_a_file(state: PipelineState) -> PipelineState:
    state.user_parts = [
        FileUIPart(media_type="image/png", url="data:image/png;base64,AA=="),
        TextUIPart(text=state.user_prompt),
    ]
    return state


async def _classify(state: PipelineState, intent: UserIntent) -> ClassifiedIntent:
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")
    returned = await classify_user_intent(ctx, intent)
    return ClassifiedIntent.model_validate(returned.return_value)


async def test_the_image_ids_are_held_by_the_attached_file(site: SiteReads) -> None:
    """An id the text does not type is held when a file is attached and the site has it."""
    state = _with_a_file(pipeline_state("plasmodb", user_prompt=IMAGE_QUESTION))

    classified = await _classify(
        state, _intent("follow_up_question", namedGeneIds=IMAGE_IDS)
    )

    assert classified.intent.named_gene_ids == IMAGE_IDS
    assert site.resolved == [IMAGE_IDS]


async def test_an_id_no_file_holds_is_refused(site: SiteReads) -> None:
    state = pipeline_state("plasmodb", user_prompt=IMAGE_QUESTION)

    with pytest.raises(ModelRetry) as refused:
        await _classify(state, _intent("follow_up_question", namedGeneIds=IMAGE_IDS))

    assert str(refused.value).startswith(
        "The researcher's message does not hold PF3D7_0709000, PF3D7_1133400, "
        "PF3D7_0102600."
    )
    assert site.resolved == []


async def test_an_attached_id_the_site_lacks_is_refused(site: SiteReads) -> None:
    state = _with_a_file(pipeline_state("plasmodb", user_prompt=IMAGE_QUESTION))

    with pytest.raises(ModelRetry) as refused:
        await _classify(
            state, _intent("follow_up_question", namedGeneIds=["PF3D7_9999999"])
        )

    assert "PF3D7_9999999" in str(refused.value)
    assert site.resolved == [["PF3D7_9999999"]]


async def test_an_attached_control_the_site_has_is_held(site: SiteReads) -> None:
    state = _with_a_file(pipeline_state("plasmodb", user_prompt="My controls."))

    classified = await _classify(
        state,
        _intent("new_strategy", namedControls={"positiveIds": IMAGE_IDS[:2]}),
    )

    assert classified.intent.named_controls is not None
    assert classified.intent.named_controls.positive_ids == IMAGE_IDS[:2]


async def test_an_id_naming_several_genes_leaves_the_others_read(
    site: SiteReads,
) -> None:
    site.several.add("PF3D7_0709000")
    state = _with_a_file(pipeline_state("plasmodb", user_prompt=IMAGE_QUESTION))

    with pytest.raises(ModelRetry) as refused:
        await _classify(state, _intent("off_topic", namedGeneIds=IMAGE_IDS))

    assert str(refused.value).startswith(
        "The researcher's message does not hold PF3D7_0709000. Name only"
    )


async def test_ids_past_one_read_are_held_and_not_refused(site: SiteReads) -> None:
    site.bound = 80
    ids = [f"PF3D7_{k:07d}" for k in range(81)]
    state = _with_a_file(pipeline_state("plasmodb", user_prompt=IMAGE_QUESTION))

    classified = await _classify(state, _intent("follow_up_question", namedGeneIds=ids))

    assert (classified.intent.named_gene_ids, site.resolved) == (ids, [ids])


async def test_ids_a_site_with_no_gene_records_cannot_read_are_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held_record_types(monkeypatch)
    state = _with_a_file(pipeline_state(ORTHOMCL, user_prompt=IMAGE_QUESTION))

    with orthomcl_gene_class() as wire:
        classified = await _classify(
            state, _intent("off_topic", namedGeneIds=IMAGE_IDS)
        )

    assert (
        classified.intent.named_gene_ids,
        wire.gene_reads.call_count,
        wire.record_type_reads.call_count,
    ) == (IMAGE_IDS, 1, 0)
