"""A card option states the value it binds, and answering it writes that value
into the spec as the card's, with no model in between."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    ParamKind,
    SinglePickValue,
    StringValue,
)
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.domain.strategy.card_answers import spec_bound_by_card
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SetValues, SlotQuestion
from pathfinder.domain.strategy.value_source import value_source
from pathfinder.tests._support.recorded_searches import suite_search

_PERCENTILE = "min_expression_percentile"
_SEARCH = "GenesByRNASeqehisHM1IMSS_Trophozoite_transcriptome_ebi_rnaSeq_RSRCPercentile"


def _published(fixture: str) -> list[ParameterInfo]:
    return format_param_info_typed(suite_search(fixture).parameters or [])


# A recorded RNA-Seq percentile sheet stands in for the trophozoite search: the
# two recorded percentile searches publish the floor alike.
_SHEETS = {
    _SEARCH: _published("search_genes_by_rnaseq_gomez_diaz_percentile"),
    "GenesWithSignalPeptide": _published("search_genes_with_signal_peptide"),
}


def _trophozoite(*, open_floor: bool) -> Criterion:
    """The amoebadb trophozoite step, its floor open or at the site default."""
    held = {
        "any_or_all": BoundValue(value=StringValue(value="all"), source="chosen"),
    }
    if not open_floor:
        held[_PERCENTILE] = BoundValue(value=NumberValue(value=80), source="default")
    return Criterion(
        id="c_troph",
        text="expressed in trophozoites",
        search_name=_SEARCH,
        resolved_params=held,
        param_display_names={_PERCENTILE: "Minimum expression percentile"},
        open_params=(
            [OpenSlot(criterion_id="c_troph", param_name=_PERCENTILE)]
            if open_floor
            else []
        ),
        measurements=[
            Measurement(kind="loosest_bound", param=_PERCENTILE, count=17, reading="1")
        ],
        result_count=None if open_floor else 6,
    )


def _floor_question() -> SlotQuestion:
    return SlotQuestion(
        question="How strictly must the genes be expressed in trophozoites?",
        dimension=ConstraintKind.PERCENTILE,
        recommended_value="1",
        criterion_id="c_troph",
        param_name=_PERCENTILE,
        options=["1", "80"],
    )


class TestAnOptionStatesItsValue:
    def test_each_label_names_the_parameter_the_value_and_its_count(self) -> None:
        typed = _floor_question().typed(_trophozoite(open_floor=False), noun="gene")

        assert [(o.id, o.label) for o in typed.options] == [
            ("1", "Minimum expression percentile 1: 17 genes"),
            ("80", "Minimum expression percentile 80: 6 genes"),
        ]

    def test_a_value_no_count_was_measured_at_is_named_alone(self) -> None:
        typed = _floor_question().typed(_trophozoite(open_floor=True), noun="gene")

        assert [o.label for o in typed.options] == [
            "Minimum expression percentile 1: 17 genes",
            "Minimum expression percentile 80",
        ]

    def test_a_count_is_named_in_the_noun_the_record_type_is_counted_in(
        self,
    ) -> None:
        criterion = _trophozoite(open_floor=False).model_copy(
            update={"result_count": 1}
        )

        typed = _floor_question().typed(criterion, noun="compound")

        assert [o.label for o in typed.options] == [
            "Minimum expression percentile 1: 17 compounds",
            "Minimum expression percentile 80: 1 compound",
        ]

    def test_without_the_criterion_the_label_is_the_value(self) -> None:
        assert [o.label for o in _floor_question().typed().options] == ["1", "80"]


class TestAnAnswerBindsTheCriterion:
    def test_the_open_floor_is_bound_as_the_cards(self) -> None:
        spec = OperationalSpec(criteria=[_trophozoite(open_floor=True)])

        bound = spec_bound_by_card(
            spec,
            SetValues(criterion_id="c_troph", params={_PERCENTILE: "1"}),
            option_id="1",
            sheets=_SHEETS,
        )

        [criterion] = bound.criteria
        assert criterion.resolved_params[_PERCENTILE] == BoundValue(
            value=StringValue(value="1"),
            source="card",
            basis="1",
            display_name="Minimum expression percentile",
            number=True,
            decimals=0,
        )
        assert criterion.open_params == []
        assert criterion.measurements == []
        assert criterion.result_count is None

    def test_a_bound_value_keeps_its_kind_and_forgets_its_count(self) -> None:
        spec = OperationalSpec(criteria=[_trophozoite(open_floor=False)])

        bound = spec_bound_by_card(
            spec,
            SetValues(criterion_id="c_troph", params={_PERCENTILE: "1"}),
            option_id="1",
            sheets=_SHEETS,
        )

        [criterion] = bound.criteria
        assert criterion.resolved_params[_PERCENTILE].value == NumberValue(value=1)
        assert criterion.resolved_params["any_or_all"].source == "chosen"
        assert criterion.result_count is None

    def test_the_spec_slot_the_answer_fills_is_closed(self) -> None:
        spec = OperationalSpec(
            criteria=[_trophozoite(open_floor=True)],
            open_slots=[
                OpenSlot(criterion_id="c_troph", param_name=_PERCENTILE),
                OpenSlot(criterion_id="c_other", param_name=_PERCENTILE),
            ],
        )

        bound = spec_bound_by_card(
            spec,
            SetValues(criterion_id="c_troph", params={_PERCENTILE: "1"}),
            option_id="1",
            sheets=_SHEETS,
        )

        assert [s.criterion_id for s in bound.open_slots] == ["c_other"]

    def test_a_binding_on_a_criterion_the_spec_lacks_changes_nothing(self) -> None:
        spec = OperationalSpec(criteria=[_trophozoite(open_floor=True)])

        bound = spec_bound_by_card(
            spec,
            SetValues(criterion_id="c_gone", params={_PERCENTILE: "1"}),
            option_id="1",
            sheets=_SHEETS,
        )

        assert bound == spec


_ORGANISM = "Entamoeba histolytica HM-1:IMSS"


def _secreted(kind: ParamKind) -> Criterion:
    """A signal-peptide step whose organism is open, of the kind its sheet gives."""
    return Criterion(
        id="c_secreted",
        text="secreted",
        search_name="GenesWithSignalPeptide",
        open_params=[
            OpenSlot(criterion_id="c_secreted", param_name="organism", param_kind=kind)
        ],
    )


class TestAnOpenSlotIsBoundInItsKind:
    def test_a_multi_pick_slot_is_bound_as_a_list_of_the_picked_term(self) -> None:
        spec = OperationalSpec(criteria=[_secreted("multi-pick-vocabulary")])

        bound = spec_bound_by_card(
            spec,
            SetValues(criterion_id="c_secreted", params={"organism": _ORGANISM}),
            option_id="entamoeba-histolytica-hm-1-imss",
            sheets=_SHEETS,
        )

        [criterion] = bound.criteria
        assert criterion.resolved_params["organism"] == BoundValue(
            value=MultiPickValue(values=[_ORGANISM]),
            source="card",
            basis="entamoeba-histolytica-hm-1-imss",
            display_name="Organism",
        )
        assert criterion.resolved_params["organism"].value.to_wire() == (
            '["Entamoeba histolytica HM-1:IMSS"]'
        )

    def test_a_single_pick_slot_is_bound_as_the_term(self) -> None:
        spec = OperationalSpec(criteria=[_secreted("single-pick-vocabulary")])

        bound = spec_bound_by_card(
            spec,
            SetValues(criterion_id="c_secreted", params={"organism": _ORGANISM}),
            option_id="o",
            sheets=_SHEETS,
        )

        [criterion] = bound.criteria
        assert criterion.resolved_params["organism"].value == SinglePickValue(
            value=_ORGANISM
        )

    def test_a_slot_only_the_spec_holds_gives_its_kind(self) -> None:
        criterion = _secreted("string").model_copy(update={"open_params": []})
        spec = OperationalSpec(
            criteria=[criterion],
            open_slots=[
                OpenSlot(
                    criterion_id="c_secreted",
                    param_name="organism",
                    param_kind="multi-pick-vocabulary",
                )
            ],
        )

        bound = spec_bound_by_card(
            spec,
            SetValues(criterion_id="c_secreted", params={"organism": _ORGANISM}),
            option_id="o",
            sheets=_SHEETS,
        )

        assert bound.criteria[0].resolved_params["organism"].value == MultiPickValue(
            values=[_ORGANISM]
        )
        assert bound.open_slots == []


class TestTheSourceOfACardValue:
    def test_a_rebound_value_the_card_set_is_the_cards(self) -> None:
        assert (
            value_source(
                NumberValue(value=1),
                placeholder=False,
                unset=False,
                request_texts=["cysteine proteases expressed in trophozoites"],
                card_value="1",
            )
            == "card"
        )

    def test_a_multi_pick_value_is_compared_by_its_wire_form(self) -> None:
        organism = MultiPickValue(values=["Entamoeba histolytica HM-1:IMSS"])

        assert (
            value_source(
                organism,
                placeholder=False,
                unset=False,
                request_texts=["cysteine proteases"],
                card_value=organism.to_wire(),
            )
            == "card"
        )
