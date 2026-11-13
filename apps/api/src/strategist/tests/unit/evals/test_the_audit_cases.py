"""The gene-model audit answer key loads, is de-identified, and names genes of its own site."""

from __future__ import annotations

import pytest
from veupathdb.wdk import load_sites_config

from strategist.evals.case import EvalCase
from strategist.evals.store import CORPUS_DIR
from strategist.platform.paths import REPO_ROOT

_FILES = sorted(CORPUS_DIR.glob("audit-*.json"))
_CASES = {path.stem: EvalCase.model_validate_json(path.read_text()) for path in _FILES}
_QA_SITES = set(load_sites_config(str(REPO_ROOT / "deploy" / "sites" / "qa.yml")).sites)
_GENE_PREFIXES = {
    "plasmodb": ("PF3D7_", "PfNF54_", "PfDd2_", "PcyM_"),
    "toxodb": ("TGGT1_", "TGME49_"),
    "tritrypdb": ("LmjF.",),
    "fungidb": ("Afu",),
    "vectorbase": ("AGAP",),
}
_DESIGN = "docs/superpowers/specs/2026-10-21-gene-model-audit-assistant-design.md"


def test_the_answer_key_holds_every_nameable_case() -> None:
    expected = {
        gene: verdict
        for case in _CASES.values()
        for gene, verdict in case.expected.verdicts.items()
    }

    assert len(_CASES) == 10
    assert expected == {
        "PfNF54_100037200": "error",
        "TGGT1_316600": "error",
        "PfNF54_000013000": "error",
        "PfNF54_000012600": "error",
        "PcyM_0736700": "error",
        "PfDd2_140076300": "error",
        "LmjF.35.3010": "error",
        "TGME49_500302": "no_error",
        "TGME49_224540": "no_error",
        "Afu8g00850": "error",
        "AGAP003685": "error",
    }


@pytest.mark.parametrize("name", sorted(_CASES))
def test_every_audit_case_loads_and_is_de_identified(name: str) -> None:
    case = _CASES[name]

    assert case.assert_de_identified()
    assert case.name == name
    assert case.assistant_id == "audit"
    assert case.expected.builds_strategy is False
    assert case.gates.policy == "leave"
    assert (case.provenance.origin, case.provenance.reference) == (
        "cataloged-failure",
        _DESIGN,
    )
    assert (case.provenance.site, case.provenance.assistant) == (case.site_id, "audit")
    assert set(case.expected.verdict_causes) == set(case.expected.verdicts) != set()


def test_every_audit_case_names_a_qa_site() -> None:
    sites = {case.site_id for case in _CASES.values()}

    assert sites == set(_GENE_PREFIXES)
    assert sites <= _QA_SITES


@pytest.mark.parametrize("name", sorted(_CASES))
def test_every_expected_gene_is_of_the_case_site_and_asked_about(name: str) -> None:
    case = _CASES[name]
    prefixes = _GENE_PREFIXES[case.site_id]

    for gene in case.expected.verdicts:
        assert gene.startswith(prefixes), gene
        assert any(gene in turn for turn in case.turns), gene
