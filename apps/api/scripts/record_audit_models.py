from pathlib import Path

import pytest
from pydantic import BaseModel
from tests._support.intron_wire import Served, load_introns
from tests._support.missing_wire import replay_record_reads
from tests._support.selenoprotein_wire import SelenoproteinWire
from tests.unit.audit.test_fusion_recorded import recording
from tests.unit.audit.test_introns_recorded import (
    AFU8,
    AGAP3685,
    AGAP7279,
    DMAW,
    DMAW_PROTEINS,
    PKAC,
    PKAC_PROTEINS,
    recorded_case,
)
from tests.unit.audit.test_strain_recorded import Strain
from veupathdb_mcp.tools.audit_fusion_tools import audit_gene_fusion
from veupathdb_mcp.tools.audit_intron_tools import audit_intron_support
from veupathdb_mcp.tools.audit_strain_tools import audit_strain_model
from veupathdb_mcp.tools.audit_tools import audit_selenoprotein_end

MODELS = (
    Path(__file__).resolve().parents[1] / "src/pathfinder/tests/fixtures/audit_models"
)


def _write(name: str, result: BaseModel) -> None:
    (MODELS / name).write_text(result.model_dump_json(indent=2) + "\n")


async def test_record_pkac(monkeypatch: pytest.MonkeyPatch) -> None:
    Served(monkeypatch, load_introns(PKAC), PKAC_PROTEINS)
    _write("pkac_introns.json", await audit_intron_support("plasmodb", "PcyM_0736700"))


async def test_record_dmaw(monkeypatch: pytest.MonkeyPatch) -> None:
    Served(monkeypatch, load_introns(DMAW), DMAW_PROTEINS)
    _write("dmaw_introns.json", await audit_intron_support("fungidb", "Afu2g18040"))


@pytest.mark.parametrize(
    ("wire", "gene", "name"),
    [
        (AFU8, "Afu8g00850", "afu8_introns.json"),
        (AGAP7279, "AGAP007279", "agap7279_introns.json"),
        (AGAP3685, "AGAP003685", "agap3685_introns.json"),
    ],
)
async def test_record_case(
    monkeypatch: pytest.MonkeyPatch, wire: str, gene: str, name: str
) -> None:
    result, _, _ = await recorded_case(monkeypatch, wire, gene)
    _write(name, result)


async def test_record_pkac_strain(monkeypatch: pytest.MonkeyPatch) -> None:
    Strain(monkeypatch, "strain_pcynM_pkac.json", "pcynM", "PcyM_07")
    result = await audit_strain_model("plasmodb", "PcyM_0736700", "PCYB_074210")
    _write("pkac_strain.json", result)


async def test_record_rpt6_fusion(monkeypatch: pytest.MonkeyPatch) -> None:
    replay_record_reads(monkeypatch, recording("pfraNilgiri_rpt6").calls)
    _write("rpt6_fusion.json", await audit_gene_fusion("plasmodb", "AK88_02763"))


async def test_record_gt1_selk(monkeypatch: pytest.MonkeyPatch) -> None:
    SelenoproteinWire(monkeypatch)
    result = await audit_selenoprotein_end("toxodb", "TGGT1_316600", "TGME49_316600")
    _write("gt1_selk.json", result)
