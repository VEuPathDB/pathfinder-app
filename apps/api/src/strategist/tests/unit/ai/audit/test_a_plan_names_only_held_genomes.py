from __future__ import annotations

from typing import Any
from uuid import uuid4

import jsonschema_rs
import pytest
from assistant_core.capabilities.refused_calls import CallRefused
from pydantic_ai.tools import RunContext

from strategist.ai.audit.deps import AuditDeps
from strategist.ai.audit.run_tools import (
    build_run_toolset,
    plan_gene_model_audit_tool,
)
from strategist.domain.audit.planning import PlanAsk
from strategist.tests._support.audit_planning import ORGANISMS, FakeSite, faked_site
from strategist.tests._support.run_context import run_context_for

_RECORDED_PLAN: dict[str, Any] = {
    "genomes": ["FungiDB"],
    "targets": [
        {"check": "intron_support", "genes": ["Afu2g18040"]},
        {"check": "intron_support", "genes": ["NCU00776"]},
    ],
}
_GENE_TARGETS_ONLY = {**_RECORDED_PLAN, "genomes": []}

type Schema = dict[str, Any]


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeSite:
    return faked_site(monkeypatch)


def _audit_context() -> RunContext[AuditDeps]:
    deps = AuditDeps(site_id="plasmodb", user_id=uuid4(), conversation_id=uuid4())
    return run_context_for(deps, tool_call_id="plan-1")


async def _audit_schema() -> Schema:
    tool = build_run_toolset().tools["plan_gene_model_audit"]
    prepared = await tool.prepare_tool_def(_audit_context())
    assert prepared is not None
    return prepared.parameters_json_schema


def _errors(schema: Schema, args: dict[str, Any]) -> list[list[str | int]]:
    validator = jsonschema_rs.validator_for(schema)
    return [list(error.instance_path) for error in validator.iter_errors(args)]


@pytest.mark.usefixtures("site")
async def test_the_plan_schema_takes_only_the_sites_organisms() -> None:
    held = await _audit_schema()

    assert held["properties"]["genomes"]["items"] == {
        "type": "string",
        "enum": ORGANISMS,
    }
    assert _errors(held, _RECORDED_PLAN) == [["genomes", 0]]
    assert _errors(held, _GENE_TARGETS_ONLY) == []


async def test_a_site_with_no_organism_takes_no_genome(site: FakeSite) -> None:
    site.organisms.clear()

    held = await _audit_schema()

    assert held["properties"]["genomes"]["maxItems"] == 0
    assert _errors(held, _RECORDED_PLAN) == [["genomes"]]
    assert _errors(held, _GENE_TARGETS_ONLY) == []


@pytest.mark.usefixtures("site")
async def test_the_recorded_site_name_is_refused_with_what_to_send() -> None:
    with pytest.raises(CallRefused) as refused:
        await plan_gene_model_audit_tool(
            _audit_context(), PlanAsk.model_validate(_RECORDED_PLAN)
        )

    assert refused.value.message == (
        "The planner starts no audit: the site holds no genome named FungiDB. "
        "A genome is one of the site's organism names, written in full. For gene "
        "targets alone, send genomes: [] with the same targets. Nothing was "
        "started and no card was shown."
    )
