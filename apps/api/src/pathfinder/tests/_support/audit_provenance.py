"""The organism report the site serves for plasmodb, read from its recorded rows."""

from __future__ import annotations

import json
from collections.abc import Sequence

from veupathdb.wdk import WDKAnswer

from pathfinder.tests._support.audit_evidence import FIXTURES


def organism_answer() -> WDKAnswer:
    records = json.loads((FIXTURES / "evidence_plasmodb_genomes.json").read_text())
    return WDKAnswer.model_validate(
        {"records": records, "meta": {"totalCount": len(records)}}
    )


async def served_organisms(site_id: str, attributes: Sequence[str]) -> WDKAnswer:
    del site_id, attributes
    return organism_answer()
