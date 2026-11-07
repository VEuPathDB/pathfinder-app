from typing import Any

from pathfinder.ai.conversation._turn_helpers import _extract_chunk
from pathfinder.ai.graph._lead_capture import LeadRunCapture
from pathfinder.ai.graph._lead_facts import show_the_facts
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.graph.test_the_reply_is_rendered_from_the_facts_it_shows import (
    _session,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_PAPER = "https://journals.plos.org/plospathogens/article?id=10.1371/journal.ppat.1"


def _links_written(payloads: list[object]) -> list[dict[str, Any]]:
    chunks = [c for p in payloads if (c := _extract_chunk(p)) is not None]
    return [c["data"] for c in chunks if c["type"] == "data-reply-links"]


def test_the_reply_links_its_records_and_the_sources_its_reads_returned() -> None:
    session = _session()
    session.sync_state = WDKSyncState(
        step_counts={"step_sp": 66, "step_orth": 129, "step_join": 9},
        wdk_step_ids={"step_sp": 101, "step_orth": 102, "step_join": 103},
    )
    deps = lead_deps(pipeline_state("microsporidiadb"), strategy_session=session)
    deps.state.turn_markers.record_listed_genes(103, ["Eint_010010"])
    deps.state.turn_markers.record_retrieved_source(_PAPER)
    deps.state.turn_markers.record_retrieved_source("38500000")
    payloads: list[object] = []

    show_the_facts(payloads.append, deps, LeadRunCapture())

    assert _links_written(payloads) == [
        {
            "links": [
                gene_record_url("microsporidiadb", "Eint_010010"),
                _PAPER,
                "https://pubmed.ncbi.nlm.nih.gov/38500000/",
            ]
        }
    ]


def test_a_reply_with_nothing_to_link_writes_no_links_part() -> None:
    deps = lead_deps(pipeline_state("microsporidiadb"), strategy_session=_session())
    payloads: list[object] = []

    show_the_facts(payloads.append, deps, LeadRunCapture())

    assert _links_written(payloads) == []
