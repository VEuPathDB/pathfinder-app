"""What changed between the spec a turn started with and the spec it produced.

An edit turn's reply claimed criteria were preserved from prose. The claim is a
comparison, so it is computed here and nowhere else.
"""

from __future__ import annotations

from collections.abc import Callable

from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.domain.strategy import CombineOp

from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.spec_diff import SpecDiff, diff_specs
from strategist.tests._support.bound_values import bound
from strategist.tests.unit.domain.strategy._builders import sets_nothing


def _criterion(cid: str, **params: ParamValue) -> Criterion:
    return Criterion(
        id=cid,
        text=f"criterion {cid}",
        search_name=f"By{cid}",
        resolved_params=bound(dict(params)),
    )


def _spec(*criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(
        goal="find kinases",
        criteria=list(criteria),
        structure=SpecStructure(root=_intersect_of(criteria)),
    )


def _intersect_of(criteria: tuple[Criterion, ...]) -> StructureNode:
    """One criterion is its leaf; more are an INTERSECT of their leaves."""
    leaves = [StructureNode(kind="leaf", criterion_id=c.id) for c in criteria]
    if len(leaves) == 1:
        return leaves[0]
    return StructureNode(kind="combine", operator=CombineOp.INTERSECT, inputs=leaves)


def _three() -> OperationalSpec:
    return _spec(
        _criterion("text"),
        _criterion("go", organism=MultiPickValue(values=["Plasmodium"])),
        _criterion("expr", min_expression_percentile=NumberValue(value=80)),
    )


def _disposition(result: SpecDiff, criterion_id: str) -> str:
    return next(c.disposition for c in result.changes if c.criterion_id == criterion_id)


class TestTheDiffNamesWhatHappened:
    def test_identical_specs_are_all_kept(self) -> None:
        result = diff_specs(_three(), _three(), sets_the_site=sets_nothing)

        assert [c.disposition for c in result.changes] == ["kept", "kept", "kept"]
        assert result.structure_changed is False

    def test_diff_reports_a_dropped_criterion(self) -> None:
        after = _spec(_criterion("text"), _criterion("go"))

        result = diff_specs(_three(), after, sets_the_site=sets_nothing)

        assert _disposition(result, "expr") == "dropped"

    def test_diff_reports_a_changed_param(self) -> None:
        before = _three()
        after = _spec(
            _criterion("text"),
            _criterion("go", organism=MultiPickValue(values=["Plasmodium"])),
            _criterion("expr", min_expression_percentile=NumberValue(value=90)),
        )

        result = diff_specs(before, after, sets_the_site=sets_nothing)

        change = next(c for c in result.changes if c.criterion_id == "expr")
        assert change.disposition == "changed"
        assert change.changed_params == {"min_expression_percentile": "90"}

    def test_diff_reports_an_added_criterion(self) -> None:
        after = _spec(
            _criterion("text"),
            _criterion("go", organism=MultiPickValue(values=["Plasmodium"])),
            _criterion("expr", min_expression_percentile=NumberValue(value=80)),
            _criterion("tm"),
        )

        result = diff_specs(_three(), after, sets_the_site=sets_nothing)

        assert _disposition(result, "tm") == "added"

    def test_a_changed_search_is_a_change_with_no_changed_params(self) -> None:
        before = _spec(_criterion("text"))
        after_criterion = _criterion("text")
        after_criterion.search_name = "GenesByTextSomethingElse"

        result = diff_specs(before, _spec(after_criterion), sets_the_site=sets_nothing)

        change = result.changes[0]
        assert change.disposition == "changed"
        assert change.changed_params == {}

    def test_a_removed_param_is_a_change(self) -> None:
        before = _spec(_criterion("go", organism=MultiPickValue(values=["Pf3D7"])))

        result = diff_specs(before, _spec(_criterion("go")), sets_the_site=sets_nothing)

        assert result.changes[0].disposition == "changed"

    def test_a_narrowed_organism_is_a_change(self) -> None:
        before = _spec(_criterion("go", organism=MultiPickValue(values=["Plasmodium"])))
        after = _spec(
            _criterion(
                "go", organism=MultiPickValue(values=["Plasmodium falciparum 3D7"])
            )
        )

        result = diff_specs(before, after, sets_the_site=sets_nothing)

        change = result.changes[0]
        assert change.disposition == "changed"
        assert change.changed_params == {
            "organism": '["Plasmodium falciparum 3D7"]',
        }


def _sets(search_name: str, param: str) -> Callable[[str, str], bool]:
    return lambda search, name: (search, name) == (search_name, param)


class TestASiteSetValueTheStepCarries:
    def test_a_read_only_value_added_at_its_site_value_is_kept(self) -> None:
        after = _spec(
            _criterion("text"),
            _criterion("go", organism=MultiPickValue(values=["Plasmodium"])),
            _criterion(
                "expr",
                min_expression_percentile=NumberValue(value=80),
                document_type=StringValue(value="gene"),
            ),
        )

        result = diff_specs(
            _three(), after, sets_the_site=_sets("Byexpr", "document_type")
        )

        assert _disposition(result, "expr") == "kept"

    def test_a_value_the_researcher_sets_added_is_a_change(self) -> None:
        after = _spec(
            _criterion("text"),
            _criterion("go", organism=MultiPickValue(values=["Plasmodium"])),
            _criterion(
                "expr",
                min_expression_percentile=NumberValue(value=80),
                document_type=StringValue(value="gene"),
            ),
        )

        result = diff_specs(_three(), after, sets_the_site=_sets("Byexpr", "other"))

        change = next(c for c in result.changes if c.criterion_id == "expr")
        assert change.changed_params == {"document_type": "gene"}


class TestAHiddenValueTheStepCarries:
    @staticmethod
    def _with_hidden_channel(criterion: Criterion) -> Criterion:
        hidden = BoundValue(
            value=SinglePickValue(value="Channel 1"), source="default", visible=False
        )
        criterion.resolved_params["channel"] = hidden
        return criterion

    def test_it_is_no_moved_value(self) -> None:
        after = _spec(
            _criterion("text"),
            _criterion("go", organism=MultiPickValue(values=["Plasmodium"])),
            self._with_hidden_channel(
                _criterion("expr", min_expression_percentile=NumberValue(value=90))
            ),
        )

        result = diff_specs(_three(), after, sets_the_site=_sets("Byexpr", "channel"))

        change = next(c for c in result.changes if c.criterion_id == "expr")
        assert change.changed_params == {"min_expression_percentile": "90"}

    def test_it_alone_keeps_the_criterion(self) -> None:
        after = _spec(
            _criterion("text"),
            _criterion("go", organism=MultiPickValue(values=["Plasmodium"])),
            self._with_hidden_channel(
                _criterion("expr", min_expression_percentile=NumberValue(value=80))
            ),
        )

        assert (
            _disposition(
                diff_specs(_three(), after, sets_the_site=_sets("Byexpr", "channel")),
                "expr",
            )
            == "kept"
        )


class TestTheStructure:
    def test_an_identical_structure_is_unchanged(self) -> None:
        assert (
            diff_specs(_three(), _three(), sets_the_site=sets_nothing).structure_changed
            is False
        )

    def test_a_different_operator_changes_the_structure(self) -> None:
        after = _three()
        assert after.structure is not None
        after.structure.root.operator = CombineOp.UNION

        assert (
            diff_specs(_three(), after, sets_the_site=sets_nothing).structure_changed
            is True
        )

    def test_a_missing_structure_on_one_side_changes_it(self) -> None:
        after = _three()
        after.structure = None

        assert (
            diff_specs(_three(), after, sets_the_site=sets_nothing).structure_changed
            is True
        )


class TestTheCounts:
    def test_a_structure_change_is_one_touch(self) -> None:
        """A rewire changes the result set, so the turn touched the strategy."""
        after = _three()
        assert after.structure is not None
        after.structure.root.operator = CombineOp.UNION

        assert (
            diff_specs(_three(), after, sets_the_site=sets_nothing).touched_count() == 1
        )

    def test_an_untouched_spec_counts_no_touch(self) -> None:
        assert (
            diff_specs(_three(), _three(), sets_the_site=sets_nothing).touched_count()
            == 0
        )

    def test_a_rewired_structure_is_named_in_the_render(self) -> None:
        after = _three()
        assert after.structure is not None
        after.structure.root.operator = CombineOp.UNION

        assert diff_specs(_three(), after, sets_the_site=sets_nothing).render() == (
            "kept 3, changed 0, added 0, dropped 0, structure rewired"
        )

    def test_an_unrewired_render_says_nothing_about_the_structure(self) -> None:
        assert diff_specs(_three(), _three(), sets_the_site=sets_nothing).render() == (
            "kept 3, changed 0, added 0, dropped 0"
        )

    def test_the_counts_summarize_the_dispositions(self) -> None:
        after = _spec(
            _criterion("text"),
            _criterion("go", organism=MultiPickValue(values=["Pvivax"])),
            _criterion("tm"),
        )

        result = diff_specs(_three(), after, sets_the_site=sets_nothing)

        assert result.kept_count == 1
        assert result.changed_count == 1
        assert result.dropped_count == 1
        assert result.added_count == 1
