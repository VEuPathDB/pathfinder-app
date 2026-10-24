from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKRecordInstance

from pathfinder.ai.audit import verdict_tool
from pathfinder.ai.audit.verdict_tool import record_gene_model_verdicts
from pathfinder.domain.audit.verdicts import GeneModelVerdict
from pathfinder.services.audit import investigation
from pathfinder.services.gene_records.genome import genome_of
from pathfinder.tests._support.audit_check_runs import (
    PAIR_ARGS,
    REFERENCE,
    RESOLVED,
    STRAIN,
    answering,
    check_deps,
    run_check,
    serve_recorded_genomes,
)
from pathfinder.tests._support.audit_model_wire import SELK_WIRE
from pathfinder.tests._support.run_context import run_context_for


@pytest.fixture(autouse=True)
def organism_reads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    return serve_recorded_genomes(monkeypatch)


async def test_a_gene_genome_is_read_once_in_an_investigation(
    monkeypatch: pytest.MonkeyPatch, organism_reads: list[tuple[str, str]]
) -> None:
    answering(monkeypatch, None)
    deps = check_deps()

    await run_check("audit_pseudogene_call", PAIR_ARGS, deps)
    await run_check("audit_pseudogene_call", PAIR_ARGS, deps)

    assert organism_reads == [("plasmodb", RESOLVED), ("plasmodb", REFERENCE)]
    assert deps.record_genomes == {
        RESOLVED: "Examplea alpha A",
        REFERENCE: "Examplea alpha R",
    }


async def test_a_verdict_holds_the_full_genome_name_and_never_the_abbreviation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = WDKRecordInstance.model_validate(SELK_WIRE.records[0].body)
    abbreviated = WDKRecordInstance.model_validate(SELK_WIRE.records[6].body)

    async def genome(site_id: str, gene: str) -> str:
        del site_id, gene
        return genome_of(recorded)

    async def store(**_: object) -> int:
        return 7

    monkeypatch.setattr(investigation, "read_gene_genome", genome)
    monkeypatch.setattr(verdict_tool, "record_verdict", store)
    answering(monkeypatch, None)
    deps = check_deps()
    await run_check("audit_pseudogene_call", PAIR_ARGS, deps)
    cite = "audit_pseudogene_call:EXA_0001:EXR_0001"

    def verdict(genome_name: str) -> GeneModelVerdict:
        return GeneModelVerdict(
            genes=(STRAIN,),
            model_genome=genome_name,
            verdict="no_error",
            cause="The call holds.",
            cites=(cite,),
        )

    short = abbreviated.attribute_text("organismAbbrev") or ""
    with pytest.raises(ModelRetry):
        await record_gene_model_verdicts(run_context_for(deps), [verdict(short)])
    stored = await record_gene_model_verdicts(
        run_context_for(deps), [verdict("Toxoplasma gondii GT1")]
    )

    assert (short, stored.return_value) == ("tgonGT1", [7])
    assert [r.organism for r in deps.records][:1] == ["Toxoplasma gondii GT1"]
