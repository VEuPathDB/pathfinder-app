from __future__ import annotations

from pathlib import Path

from pathfinder.ai.audit.facts import audit_run_fact
from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.domain.reply_references import ProseFault, prose_faults
from pathfinder.domain.turn_facts import SourceFact, TurnFacts
from pathfinder.services.audit.views import AuditRunView

_VIEW = Path(__file__).with_name("audit_run_cae8f3a8.json")
_GENE = "Afu2g18040"
_RUN = "stat_e109e8a5"
_CLOSING = (
    "The independent reviews agreed on all sampled findings, so this result was "
    f"retained rather than treated as disputed. [cite:{_RUN}.agreement.text]"
)


def _reply(certainty: str) -> str:
    return (
        f"For [record:{_GENE}], the audit found a **shifted splice site**: the "
        "annotated splice junctions were not supported by the RNA-seq reads, while "
        "nearby alternative junctions were supported and preserved the coding "
        f"structure. [cite:{_RUN}.errorTypes.0.cause]\n\nThe finding is "
        f"**[stat:{_RUN}.{certainty}] certainty**. {_CLOSING}"
    )


def _facts() -> TurnFacts:
    view = AuditRunView.model_validate_json(_VIEW.read_text())
    url = f"https://qa.fungidb.org/fungidb.qa/app/record/gene/{_GENE}"
    return TurnFacts(
        audit_statistics=[audit_run_fact(view)],
        named_genes=[SourceFact(url=url, record_id=_GENE)],
    )


def test_a_gene_given_its_error_types_certainty_is_refused() -> None:
    assert prose_faults(_reply("errorTypes.0.certainty"), _facts()) == [
        ProseFault(
            token=f"[stat:{_RUN}.errorTypes.0.certainty]",
            kind="group_certainty",
            references=(f"[stat:{_RUN}.errorTypes.0.reviewed.0.certainty]",),
        )
    ]


def test_a_gene_given_its_findings_certainty_stands() -> None:
    assert prose_faults(_reply("headline.0.certainty"), _facts()) == []


def test_the_run_fact_holds_the_stored_certainty_of_each_finding() -> None:
    fact = audit_run_fact(AuditRunView.model_validate_json(_VIEW.read_text()))

    assert (
        fact.value("errorTypes.0.certainty"),
        fact.value("headline.0.certainty"),
    ) == ("high", "medium")


def test_the_refusal_names_the_findings_own_certainty() -> None:
    (fault,) = prose_faults(_reply("errorTypes.0.certainty"), _facts())

    assert unrendered_prose_message([fault]).splitlines()[-1] == (
        f"- ``[stat:{_RUN}.errorTypes.0.certainty]`` is the certainty of a group "
        "of findings, and the reply gives it to one gene: write "
        f"``[stat:{_RUN}.errorTypes.0.reviewed.0.certainty]``, the certainty of "
        "that gene's own finding."
    )
