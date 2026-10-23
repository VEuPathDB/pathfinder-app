"""Each target is confirmed by its library check; a failure says failed or unreached."""

from __future__ import annotations

from typing import Literal

import httpx
import pytest
from fastmcp.exceptions import ToolError
from veupathdb.errors import DataParsingError, WDKError
from veupathdb.jbrowse import JBrowseError

from pathfinder.domain.audit.confirmations import (
    FusionConfirmation,
    IntronConfirmation,
    LengthConfirmation,
    MissingGeneConfirmation,
    OrganelleConfirmation,
    PseudogeneConfirmation,
    SelenoproteinConfirmation,
    StrainConfirmation,
)
from pathfinder.domain.audit.scope import (
    GenePairTarget,
    GeneTarget,
    MissingGeneTarget,
    OrganelleTarget,
    SingleGeneTarget,
)
from pathfinder.services.audit import checks
from pathfinder.services.audit.checks import UnitFailure, confirm_target
from pathfinder.services.audit.units import SignInNeededError
from pathfinder.tests._support.audit import (
    GT1_SELK,
    ME49_SELK,
    NF54,
    NF54_PIGA,
    PIGA,
    PIGA_INTACT,
    SELK_STOPS,
    not_checked_audit,
    split_audit,
)
from pathfinder.tests._support.audit_answers import (
    ARI_NAC,
    CYTB,
    FRAGILE_RPT6,
    GT1,
    NF54_MITO,
    PCYB_PKAC,
    PCYM_PKAC,
    fusion,
    missing,
    organelle,
    strain,
)
from pathfinder.tests._support.audit_introns import INTRON_GENE, intron_audit
from pathfinder.tests._support.audit_wire import (
    DD2_YIP1,
    SITE,
    UNFLAGGED_STRAIN,
    yip1_records,
)


def _caused(message: str, cause: BaseException) -> ToolError:
    error = ToolError(message)
    error.__cause__ = cause
    return error


async def test_a_pseudogene_target_calls_the_tool_strain_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str, str]] = []

    async def tool(site_id: str, strain_gene: str, reference_gene: str) -> object:
        asked.append((site_id, strain_gene, reference_gene))
        return PIGA_INTACT

    monkeypatch.setattr(checks, "audit_pseudogene_call", tool)
    found = await confirm_target(
        "plasmodb", GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA))
    )
    assert found == PseudogeneConfirmation(result=PIGA_INTACT)
    assert asked == [("plasmodb", NF54_PIGA, PIGA)]


async def test_each_check_reaches_its_own_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    split = split_audit("NF54_A", "NF54_B", reference_gene="R1")
    typical = not_checked_audit(["PcyM_0736700"], "TYPICAL", reference_gene="R1")
    asked: list[tuple[str, ...]] = []

    async def selenoprotein(site_id: str, gene: str, reference_gene: str) -> object:
        asked.append((site_id, gene, reference_gene))
        return SELK_STOPS

    async def length(site_id: str, gene: str) -> object:
        asked.append((site_id, gene))
        return typical

    async def pair(site_id: str, gene_a: str, gene_b: str) -> object:
        asked.append((site_id, gene_a, gene_b))
        return split

    monkeypatch.setattr(checks, "audit_selenoprotein_end", selenoprotein)
    monkeypatch.setattr(checks, "audit_gene_length", length)
    monkeypatch.setattr(checks, "audit_gene_split", pair)
    sec = GenePairTarget(check="selenoprotein_end", genes=(GT1_SELK, ME49_SELK))
    single = SingleGeneTarget(check="gene_length", genes=("PcyM_0736700",))
    halves = GenePairTarget(check="gene_split", genes=("NF54_B", "NF54_A"))
    assert await confirm_target("toxodb", sec) == SelenoproteinConfirmation(
        result=SELK_STOPS
    )
    assert await confirm_target("plasmodb", single) == LengthConfirmation(
        check="gene_length", result=typical
    )
    assert await confirm_target("plasmodb", halves) == LengthConfirmation(
        check="gene_split", result=split
    )
    assert asked == [
        ("toxodb", GT1_SELK, ME49_SELK),
        ("plasmodb", "PcyM_0736700"),
        ("plasmodb", "NF54_A", "NF54_B"),
    ]


async def test_a_fusion_target_calls_the_tool_with_its_gene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str]] = []
    answer = fusion("EXTRA_MATCHES_NEIGHBOUR")

    async def tool(site_id: str, gene: str) -> object:
        asked.append((site_id, gene))
        return answer

    monkeypatch.setattr(checks, "audit_gene_fusion", tool)
    found = await confirm_target(
        "plasmodb", SingleGeneTarget(check="gene_fusion", genes=(FRAGILE_RPT6,))
    )
    assert found == FusionConfirmation(result=answer)
    assert asked == [("plasmodb", FRAGILE_RPT6)]


async def test_an_intron_target_calls_the_tool_with_its_gene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str]] = []
    answer = intron_audit("UNSUPPORTED_REPLACED")

    async def tool(site_id: str, gene: str) -> object:
        asked.append((site_id, gene))
        return answer

    monkeypatch.setattr(checks, "audit_intron_support", tool)
    found = await confirm_target(
        "toxodb", SingleGeneTarget(check="intron_support", genes=(INTRON_GENE,))
    )
    assert found == IntronConfirmation(result=answer)
    assert asked == [("toxodb", INTRON_GENE)]


async def test_a_strain_target_calls_the_tool_strain_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str, str]] = []
    answer = strain("NO_RELATIVES")

    async def tool(site_id: str, strain_gene: str, reference_gene: str) -> object:
        asked.append((site_id, strain_gene, reference_gene))
        return answer

    monkeypatch.setattr(checks, "audit_strain_model", tool)
    found = await confirm_target(
        "plasmodb",
        GenePairTarget(check="strain_model", genes=(PCYM_PKAC, PCYB_PKAC)),
    )
    assert found == StrainConfirmation(result=answer)
    assert asked == [("plasmodb", PCYM_PKAC, PCYB_PKAC)]


async def test_a_missing_gene_target_calls_the_tool_with_the_absent_organism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str, str]] = []
    answer = missing("IN_DNA_UNANNOTATED")

    async def tool(site_id: str, example_gene: str, absent_organism: str) -> object:
        asked.append((site_id, example_gene, absent_organism))
        return answer

    monkeypatch.setattr(checks, "audit_missing_gene", tool)
    target = MissingGeneTarget(
        check="missing_gene", genes=(ARI_NAC,), absent_organism=GT1
    )
    assert await confirm_target("toxodb", target) == MissingGeneConfirmation(
        result=answer
    )
    assert asked == [("toxodb", ARI_NAC, GT1)]


async def test_an_organelle_target_calls_the_tool_organism_contig_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str, str, str]] = []
    answer = organelle("SPLIT_AT_JOIN")

    async def tool(
        site_id: str, organism: str, sequence_id: str, reference_gene: str
    ) -> object:
        asked.append((site_id, organism, sequence_id, reference_gene))
        return answer

    monkeypatch.setattr(checks, "audit_organelle_gene", tool)
    target = OrganelleTarget(
        check="organelle_join", genes=(CYTB,), organism=NF54, sequence_id=NF54_MITO
    )
    assert await confirm_target("plasmodb", target) == OrganelleConfirmation(
        result=answer
    )
    assert asked == [("plasmodb", NF54, NF54_MITO, CYTB)]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (
            _caused(
                "plasmodb did not answer the audit reads: ConnectError refused",
                httpx.ConnectError("refused"),
            ),
            "unreached",
        ),
        (
            _caused("VEuPathDB service error", WDKError("upstream failed", status=502)),
            "unreached",
        ),
        (
            _caused(
                "GET https://qa.plasmodb.org/x answered 503",
                JBrowseError("GET", "https://qa.plasmodb.org/x", 503),
            ),
            "unreached",
        ),
        (_caused("gene not found", WDKError("gene not found", status=404)), "failed"),
        (
            _caused(
                "WDK GeneByLocusTag report served 10 records of a total of 12",
                DataParsingError(
                    "WDK GeneByLocusTag report served 10 records of a total of 12"
                ),
            ),
            "failed",
        ),
        (ToolError("NOT_A_GENE names no gene of plasmodb"), "failed"),
    ],
)
async def test_a_tool_error_is_failed_or_unreached(
    monkeypatch: pytest.MonkeyPatch,
    error: ToolError,
    status: Literal["failed", "unreached"],
) -> None:
    async def tool(site_id: str, gene: str) -> object:
        raise error

    monkeypatch.setattr(checks, "audit_gene_length", tool)
    found = await confirm_target(
        "plasmodb", SingleGeneTarget(check="gene_length", genes=("NOT_A_GENE",))
    )
    assert found == UnitFailure(status=status, message=str(error))


async def test_the_library_refuses_a_strain_gene_its_site_does_not_flag() -> None:
    with yip1_records() as report:
        found = await confirm_target(SITE, UNFLAGGED_STRAIN)
    assert found == UnitFailure(
        status="failed",
        message=(
            f"{DD2_YIP1} is not flagged a pseudogene on plasmodb (is_pseudo: No); "
            "the check reads a strain gene the site calls a pseudogene"
        ),
    )
    assert report.call_count == 2


async def test_a_gene_record_with_no_transcript_table_is_failed() -> None:
    with yip1_records(readable=False) as report:
        found = await confirm_target(SITE, UNFLAGGED_STRAIN)
    assert found == UnitFailure(
        status="failed",
        message=(
            f"the gene record of {DD2_YIP1} on plasmodb gives no readable "
            "GeneTranscripts"
        ),
    )
    assert report.call_count == 1


async def test_an_unexpected_failure_is_not_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def tool(site_id: str, gene: str) -> object:
        msg = "a library bug"
        raise RuntimeError(msg)

    monkeypatch.setattr(checks, "audit_gene_length", tool)
    with pytest.raises(RuntimeError, match="a library bug"):
        await confirm_target(
            "plasmodb", SingleGeneTarget(check="gene_length", genes=("X",))
        )


_GENOME_CHECKS: dict[str, GeneTarget] = {
    "audit_gene_fusion": SingleGeneTarget(check="gene_fusion", genes=(FRAGILE_RPT6,)),
    "audit_strain_model": GenePairTarget(
        check="strain_model", genes=(PCYM_PKAC, PCYB_PKAC)
    ),
    "audit_missing_gene": MissingGeneTarget(
        check="missing_gene", genes=(ARI_NAC,), absent_organism=GT1
    ),
    "audit_organelle_gene": OrganelleTarget(
        check="organelle_join", genes=(CYTB,), organism=NF54, sequence_id=NF54_MITO
    ),
}
_HALF_THE_CIRCLE = (
    "the reference codes 376 residues, 1128 bases, more than half of the "
    "2000-base circle; a turn by half cannot place it whole"
)


@pytest.mark.parametrize("tool", list(_GENOME_CHECKS))
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (_caused(_HALF_THE_CIRCLE, ValueError(_HALF_THE_CIRCLE)), "failed"),
        (ToolError(f"{ARI_NAC} names no gene of toxodb"), "failed"),
        (
            _caused("VEuPathDB service error", WDKError("upstream failed", status=502)),
            "unreached",
        ),
    ],
)
async def test_a_refused_genome_check_is_failed_or_unreached(
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    error: ToolError,
    status: Literal["failed", "unreached"],
) -> None:
    async def refusing(*args: str) -> object:
        del args
        raise error

    monkeypatch.setattr(checks, tool, refusing)
    found = await confirm_target("plasmodb", _GENOME_CHECKS[tool])
    assert found == UnitFailure(status=status, message=str(error))


@pytest.mark.parametrize("tool", list(_GENOME_CHECKS))
async def test_a_genome_check_refused_for_sign_in_halts_the_run(
    monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    async def refusing(*args: str) -> object:
        del args
        refused = "unauthorized"
        raise _caused(refused, WDKError(refused, status=401))

    monkeypatch.setattr(checks, tool, refusing)
    with pytest.raises(SignInNeededError, match="sign-in needed"):
        await confirm_target("plasmodb", _GENOME_CHECKS[tool])
