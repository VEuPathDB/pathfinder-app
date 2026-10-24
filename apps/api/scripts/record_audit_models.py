from pathlib import Path

import pytest
from tests._support.intron_wire import Served, load_introns
from tests.unit.audit.test_introns_recorded import (
    AFU8,
    AGAP3685,
    AGAP7279,
    PKAC,
    PKAC_PROTEINS,
    recorded_case,
)
from veupathdb_mcp.audit import IntronAudit
from veupathdb_mcp.tools.audit_intron_tools import audit_intron_support

MODELS = (
    Path(__file__).resolve().parents[1] / "src/pathfinder/tests/fixtures/audit_models"
)


def _write(name: str, result: IntronAudit) -> None:
    (MODELS / name).write_text(result.model_dump_json(indent=2) + "\n")


async def test_record_pkac(monkeypatch: pytest.MonkeyPatch) -> None:
    Served(monkeypatch, load_introns(PKAC), PKAC_PROTEINS)
    _write("pkac_introns.json", await audit_intron_support("plasmodb", "PcyM_0736700"))


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
