from __future__ import annotations

from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.ai.lead.withheld_reply import withholds
from pathfinder.domain.record_facts import SourceFact
from pathfinder.domain.reply_references import ProseFault, prose_faults
from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.domain.turn_facts import TurnFacts

_RUN = "stat_80015bb0"
_KEYED = f"{_RUN}.errorTypes.shifted_splice_site.reviewed.0.certainty"
_PLACED = f"{_RUN}.errorTypes.0.reviewed.0.certainty"
_RECORDED = (
    "For [record:Afu2g18040], the audit found a **shifted splice site**. The "
    f"finding's certainty is [stat:{_KEYED}]."
)


def _facts() -> TurnFacts:
    rows = [
        StatisticRowFact(
            name="errorTypes.0.errorType",
            value="shifted splice site",
            form="word",
            code="shifted_splice_site",
        ),
        StatisticRowFact(name="errorTypes.0.count", value="2"),
        StatisticRowFact(name="errorTypes.0.reviewed.0.id", value="1"),
        StatisticRowFact(
            name="errorTypes.0.reviewed.0.certainty",
            value="medium",
            form="word",
            code="medium",
        ),
        StatisticRowFact(name="errorTypes.0.reviewed.1.id", value="2"),
        StatisticRowFact(
            name="errorTypes.0.reviewed.1.certainty",
            value="high",
            form="word",
            code="high",
        ),
    ]
    run = StatisticFact(id=_RUN, kind="audit_run", title="Audit run", rows=rows)
    gene = SourceFact(
        url="https://qa.fungidb.org/fungidb.qa/app/record/gene/Afu2g18040",
        record_id="Afu2g18040",
    )
    return TurnFacts(audit_statistics=[run], sources=[gene])


def _fault(prose: str) -> ProseFault:
    (fault,) = prose_faults(prose, _facts())
    return fault


def test_a_list_item_named_by_a_code_it_holds_is_refused_with_its_place() -> None:
    assert _fault(_RECORDED) == ProseFault(
        token=f"[stat:{_KEYED}]",
        kind="keyed_reference",
        references=(f"[stat:{_PLACED}]",),
    )


def test_a_cite_named_by_a_code_keeps_its_kind() -> None:
    fault = _fault(_RECORDED.replace("[stat:", "[cite:"))

    assert (fault.kind, fault.references) == (
        "keyed_reference",
        (f"[cite:{_PLACED}]",),
    )


def test_the_refusal_names_the_place_that_renders_the_value() -> None:
    message = unrendered_prose_message([_fault(_RECORDED)])

    assert message.splitlines()[-1] == (
        f"- ``[stat:{_KEYED}]`` names a list item by a value it holds, and a "
        "row names each item by its place in the list: write "
        f"``[stat:{_PLACED}]``, which renders it."
    )


def test_a_keyed_reference_renders_nothing_and_is_withheld() -> None:
    assert withholds([_fault(_RECORDED)])


def test_the_placed_reference_renders_the_certainty() -> None:
    prose = f"The finding's certainty is [stat:{_PLACED}]."

    assert prose_faults(prose, _facts()) == []
