"""The classification gate holds a classification to the site's organisms and genes."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart, TextUIPart
from veupathdb_mcp.gene_lookup import GeneResolveResult, GeneResult

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import classification_gate
from pathfinder.ai.lead.intent import ClassifiedIntent, IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
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


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> SiteReads:
    """Serve each site's recorded organisms, and resolve the image's ids as genes."""
    reads = SiteReads(genes=IMAGE_IDS)

    async def _organisms(site_id: str) -> list[str]:
        reads.organisms.append(site_id)
        return recorded_organisms(site_id)

    async def _resolve(site_id: str, gene_ids: list[str]) -> GeneResolveResult:
        del site_id
        reads.resolved.append(gene_ids)
        found = [GeneResult(gene_id=g) for g in gene_ids if g.upper() in reads.genes]
        return GeneResolveResult(records=found, total_count=len(found))

    monkeypatch.setattr(classification_gate, "list_organisms", _organisms)
    monkeypatch.setattr(classification_gate, "resolve_gene_ids", _resolve)
    return reads


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


@pytest.mark.parametrize(
    ("site_id", "message", "organism"),
    [
        ("microsporidiadb", SPORE_WALL, "Encephalitozoon cuniculi GB-M1"),
        ("trichdb", BSPA, "Trichomonas vaginalis G3"),
    ],
)
async def test_an_organism_and_a_gene_class_is_no_context_statement(
    site: SiteReads, site_id: str, message: str, organism: str
) -> None:
    """A message naming a site organism and what to find in it asks for a build."""
    state = pipeline_state(site_id, user_prompt=message)

    with pytest.raises(ModelRetry) as refused:
        await _classify(state, _intent("context_statement"))

    assert f'"{organism}"' in str(refused.value)
    assert "new_strategy" in str(refused.value)
    assert site.organisms == [site_id]
    built = await _classify(state, _intent("new_strategy"))
    assert built.intent.classification is IntentClassification.NEW_STRATEGY


async def test_a_context_statement_naming_no_site_organism_stands(
    site: SiteReads,
) -> None:
    state = pipeline_state("trichdb", user_prompt="I run a drug resistance lab.")

    classified = await _classify(state, _intent("context_statement"))

    assert classified.intent.classification is IntentClassification.CONTEXT_STATEMENT
    assert site.organisms == ["trichdb"]


async def test_an_organism_alone_is_a_context_statement(site: SiteReads) -> None:
    state = pipeline_state("trichdb", user_prompt="Trichomonas vaginalis G3.")

    classified = await _classify(state, _intent("context_statement"))

    assert classified.intent.classification is IntentClassification.CONTEXT_STATEMENT


async def test_an_image_of_site_genes_is_not_off_topic(site: SiteReads) -> None:
    """The ids the attached image shows are genes of the site, so it is in scope."""
    state = _with_a_file(pipeline_state("plasmodb", user_prompt=IMAGE_QUESTION))

    with pytest.raises(ModelRetry) as refused:
        await _classify(state, _intent("off_topic", namedGeneIds=IMAGE_IDS))

    assert "PF3D7_0709000, PF3D7_1133400, PF3D7_0102600" in str(refused.value)
    assert site.resolved == [IMAGE_IDS]


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


async def test_a_typed_site_gene_is_not_off_topic(site: SiteReads) -> None:
    state = pipeline_state(
        "plasmodb", user_prompt="Write a poem about pf3d7_1133400 please."
    )

    with pytest.raises(ModelRetry) as refused:
        await _classify(state, _intent("off_topic"))

    assert "pf3d7_1133400" in str(refused.value)
    assert site.resolved == [["pf3d7_1133400"]]


async def test_a_message_with_no_site_gene_stays_off_topic(site: SiteReads) -> None:
    state = pipeline_state("plasmodb", user_prompt="Write a haiku about spring.")

    classified = await _classify(state, _intent("off_topic"))

    assert classified.intent.classification is IntentClassification.OFF_TOPIC
    assert site.resolved == []
    assert site.organisms == []
