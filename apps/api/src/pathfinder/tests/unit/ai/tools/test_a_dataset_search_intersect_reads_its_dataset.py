"""``set_structure`` reads the organism of a search that marks no organism
parameter from the one dataset that names it."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.domain.strategy.operational_spec import Criterion, StructureNode
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.organism_reads import serve_organism_reads
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


def _ctx(state: AgentToolState) -> RunContext[AgentDeps]:
    return agent_run_context(agent_state=state)


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _intersect(*inputs: StructureNode) -> StructureNode:
    return StructureNode(
        kind="combine", operator=CombineOp.INTERSECT, inputs=list(inputs)
    )


def _drafted_root(state: AgentToolState) -> StructureNode:
    structure = state.operational_spec_draft.structure
    assert structure is not None
    return structure.root


def _signal_peptide(criterion_id: str, organism: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=f"{organism} genes that have a predicted signal peptide",
        search_name="GenesWithSignalPeptide",
        role="seed",
        organism_param="organism",
        resolved_params=bound({"organism": MultiPickValue(values=[organism])}),
    )


def _dataset_search(criterion_id: str, search_name: str, organism: str) -> Criterion:
    """A percentile search as its site publishes it: no organism parameter, and
    the organism of the one dataset that names it."""
    return Criterion(
        id=criterion_id,
        text=f"{organism} genes above the 80th expression percentile",
        search_name=search_name,
        role="filter",
        dataset_organisms=[organism],
        resolved_params=bound({"min_expression_percentile": StringValue(value="80")}),
    )


_OOCYSTS = "GenesByRNASeqchomTU502_Widmer_oocysts_ebi_rnaSeq_RSRCPercentile"
_TROPHOZOITES = (
    "GenesByRNASeqehisHM1IMSS_Trophozoite_transcriptome_ebi_rnaSeq_RSRCPercentile"
)


class TestAnIntersectWithADatasetSearch:
    """A search that marks no organism parameter runs on its dataset's organism."""

    @pytest.mark.asyncio
    async def test_a_dataset_search_of_another_species_is_refused(self) -> None:
        st = AgentToolState()
        st.frame_set_criterion(
            _signal_peptide("c_sp", "Cryptosporidium meleagridis strain UKMEL1")
        )
        st.frame_set_criterion(
            _dataset_search("c_oocysts", _OOCYSTS, "Cryptosporidium hominis TU502")
        )

        with pytest.raises(ModelRetry) as exc:
            await set_structure(
                _ctx(st),
                root=_intersect(_leaf("c_sp"), _leaf("c_oocysts")),
            )

        assert str(exc.value) == (
            "The structure is refused: Cannot INTERSECT steps with different "
            "organism scopes (Cryptosporidium meleagridis strain UKMEL1 vs "
            "Cryptosporidium hominis TU502). Gene IDs from different species never "
            "match, so this always returns 0 results. The "
            f"{_OOCYSTS} search runs on an experiment of Cryptosporidium hominis "
            "TU502, and no parameter changes that organism. Map that side to "
            "Cryptosporidium meleagridis strain UKMEL1 with a GenesByOrthologs "
            "transform. Nothing was recorded."
        )
        assert st.operational_spec_draft.structure is None

    @pytest.mark.asyncio
    async def test_a_dataset_search_of_the_same_organism_is_written(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_organism_reads(monkeypatch, ["Entamoeba histolytica HM-1:IMSS"])
        st = AgentToolState()
        st.frame_set_criterion(
            Criterion(
                id="c_go",
                text="Entamoeba histolytica HM-1:IMSS cysteine-type peptidases",
                search_name="GenesByGoTerm",
                role="seed",
                organism_param="organism",
                resolved_params=bound(
                    {
                        "organism": MultiPickValue(
                            values=["Entamoeba histolytica HM-1:IMSS"]
                        )
                    }
                ),
            )
        )
        st.frame_set_criterion(
            _dataset_search(
                "c_trophozoites", _TROPHOZOITES, "Entamoeba histolytica HM-1:IMSS"
            )
        )

        await set_structure(
            _ctx(st),
            root=_intersect(_leaf("c_go"), _leaf("c_trophozoites")),
        )

        assert _drafted_root(st).operator == CombineOp.INTERSECT
