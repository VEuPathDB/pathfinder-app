from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from assistant_core.conversation.serde import build_checkpoint_serde
from assistant_core.graph.turn_state import PendingApproval
from pydantic import TypeAdapter

from strategist.ai.graph.state import StrategyDomainState, VerificationDigest
from strategist.assistants.strategist_spec import STRATEGIST_CHECKPOINT_TYPES
from strategist.domain.site_checks import SiteCheckGap
from strategist.domain.strategy.question_options import Keep, Withdraw
from strategist.domain.strategy.readings import ReadValues
from strategist.domain.unmet_requirements import unmet_requirement_ids
from strategist.tests._support.stored_domains import (
    stored_domain,
    stored_domain_blob,
)
from strategist.tests.unit.ai.lead.conftest import pipeline_state

_STORED = "domain-with-kind-value-keys"


def _read() -> StrategyDomainState:
    serde = build_checkpoint_serde(STRATEGIST_CHECKPOINT_TYPES)
    restored = serde.loads_typed(stored_domain_blob(_STORED))
    assert type(restored) is StrategyDomainState
    return restored


def _ids(domain: StrategyDomainState) -> dict[str, str]:
    return {
        c.requested_value: c.id
        for c in [
            *domain.requirements,
            *(r.constraint for r in domain.retired_requirements),
        ]
    }


def test_every_stored_requirement_gets_its_own_id() -> None:
    ids = _ids(_read())

    assert sorted(ids) == [
        "Plasmodium",
        "Plasmodium falciparum 3D7",
        "proteins",
        "signal peptide",
    ]
    assert len(set(ids.values())) == 4
    assert all(ids.values())


def test_a_stored_replacement_names_its_successor_by_id() -> None:
    domain = _read()

    [retired] = domain.retired_requirements

    assert retired.lifecycle.model_dump() == {
        "state": "replaced",
        "by": _ids(domain)["Plasmodium falciparum 3D7"],
    }


def test_a_stored_record_type_loads_untyped_and_its_role_is_dropped() -> None:
    domain = _read()

    [proteins] = [c for c in domain.requirements if c.requested_value == "proteins"]
    assert (proteins.value, "record_roles" in domain.model_dump()) == (None, False)


def test_a_stored_card_binds_the_requirement_by_id() -> None:
    domain = _read()
    signal = _ids(domain)["signal peptide"]

    [question] = domain.open_questions

    assert [o.binding for o in question.options] == [
        Withdraw(constraint_id=signal),
        Keep(constraint_id=signal),
        ReadValues(
            criterion_id="c1",
            params={"p": "SignalP"},
            reading="SignalP",
            replaces=[signal],
        ),
    ]


def test_a_stored_reading_names_what_it_replaces_by_id() -> None:
    domain = _read()
    signal = _ids(domain)["signal peptide"]
    assert domain.operational_spec is not None

    reading = domain.operational_spec.criteria[0].accepted_reading

    assert reading is not None
    assert (reading.replaces, reading.stand_in) == ([signal], signal)


def test_a_stored_check_names_its_requirement_by_id() -> None:
    domain = _read()
    strain = _ids(domain)["Plasmodium falciparum 3D7"]
    assert domain.site_verdict is not None

    [check] = domain.site_verdict.review.checks
    [gap] = domain.site_verdict.gaps

    assert check.requirement == strain
    assert gap == SiteCheckGap(check=check)


def test_this_messages_additions_are_the_held_requirements() -> None:
    domain = _read()

    assert domain.turn_markers.requirements_added == [
        c
        for c in domain.requirements
        if c.requested_value == "Plasmodium falciparum 3D7"
    ]


def test_a_domain_read_twice_keeps_its_ids() -> None:
    serde = build_checkpoint_serde(STRATEGIST_CHECKPOINT_TYPES)
    once = _read()

    again = serde.loads_typed(serde.dumps_typed(once))

    assert again == once


def test_a_turn_parked_on_a_stored_domain_reads_its_verdict_by_id() -> None:
    domain = _read()
    strain = _ids(domain)["Plasmodium falciparum 3D7"]

    state = pipeline_state(
        "plasmodb",
        user_prompt="only Plasmodium falciparum 3D7",
        user_message_id=UUID(int=2),
        domain=domain,
    )
    state.pending_approval = PendingApproval(
        phase="lead",
        tool_call_id="call_card",
        tool_name="consult_user",
        user_message_id=UUID(int=2),
    )

    verdict = state.turn_verdict
    assert verdict is not None
    assert (
        unmet_requirement_ids(verdict.gaps),
        [c.requirement for c in verdict.review.checks],
        [c.id for c in state.turn_markers.requirements_added],
    ) == ([strain], [strain], [strain])


def test_a_stored_domain_read_twice_gets_the_same_ids() -> None:
    assert _ids(_read()) == _ids(_read())


def test_a_retired_copy_shares_the_id_of_the_live_requirement() -> None:
    stored = stored_domain(_STORED)
    [proteins] = [
        c
        for c in TypeAdapter(list[dict[str, object]]).validate_python(
            stored["requirements"]
        )
        if c["requested_value"] == "proteins"
    ]
    retired = {
        "constraint": proteins,
        "lifecycle": {"state": "withdrawn", "turn_id": ""},
    }
    domain = StrategyDomainState.model_validate(
        {**stored, "retired_requirements": [retired]}
    )

    [live] = [c.id for c in domain.requirements if c.requested_value == "proteins"]
    assert domain.retired_requirements[0].constraint.id == live


def test_a_stored_id_hashes_the_whole_key() -> None:
    values = ["Plasmodium falciparum 3D7", "Plasmodium falciparum HB3"]
    stored = [
        {
            "kind": "organism",
            "requested_value": v,
            "label": v,
            "source": "user_explicit",
        }
        for v in values
    ]

    domain = StrategyDomainState.model_validate({"requirements": stored})

    assert [c.id for c in domain.requirements] == [
        sha256(f"organism:{v}".encode()).hexdigest()[:12] for v in values
    ]
    assert len({c.id for c in domain.requirements}) == 2


def test_a_stored_verdict_naming_an_unrecorded_requirement_is_dropped() -> None:
    stored = stored_domain(_STORED)
    spec_only = {
        "evidence": "the strategy states tm_count = 1",
        "kind": "other",
        "requirement": "other:at least 2 transmembrane domains",
        "status": "fail",
        "subject": "at least 2 transmembrane domains",
        "why_unchecked": None,
    }
    verdict = VerificationDigest.model_validate(stored["site_verdict"])
    checks = [*verdict.review.model_dump()["checks"], spec_only]

    domain = StrategyDomainState.model_validate(
        {
            **stored,
            "site_verdict": {
                **verdict.model_dump(),
                "review": {**verdict.review.model_dump(), "checks": checks},
            },
        }
    )

    assert (domain.site_verdict, domain.verified_revision) == (None, "")
