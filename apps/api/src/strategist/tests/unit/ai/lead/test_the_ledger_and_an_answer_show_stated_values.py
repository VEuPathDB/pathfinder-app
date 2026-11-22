from __future__ import annotations

from assistant_core.graph.turn_state import UserQuestionAnswer
from veupathdb.domain.parameters import FilterValue, MultiPickValue

from strategist.ai.lead.answers_text import answers_text
from strategist.ai.lead.ledger_render import render_frame_full
from strategist.ai.lead.ledger_sections import FrameSection, assumption_constraints
from strategist.domain.strategy.operational_spec import Criterion, OperationalSpec
from strategist.domain.strategy.question_options import SetValues, TypedOption
from strategist.domain.strategy.questions import OpenQuestion
from strategist.tests._support.bound_values import bound

_PF = "Plasmodium falciparum 3D7"
_P01 = "Plasmodium vivax P01"
_NO_CLAUSE = "[]"


def _spec() -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_snps",
                text="SNPs in vivax",
                search_name="GenesByNgsSnps",
                resolved_params=bound(
                    {
                        "organismSinglePick": MultiPickValue(values=[_P01]),
                        "variation_sample_meta": FilterValue(),
                    },
                    chosen={
                        "organismSinglePick": "the thread names vivax",
                        "variation_sample_meta": "no sample is named",
                    },
                ),
            )
        ]
    )


def test_an_assumed_value_is_its_stated_form() -> None:
    assumed = {
        g.constraint.label: (g.constraint.requested_value, g.realized_value)
        for g in assumption_constraints(_spec())
    }

    assert assumed == {
        "organismSinglePick": (f'["{_P01}"]', f'["{_P01}"]'),
        "variation_sample_meta": (_NO_CLAUSE, _NO_CLAUSE),
    }


def test_the_frame_section_shows_each_value_as_stated() -> None:
    shown = render_frame_full(FrameSection(spec=_spec()))

    assert shown.splitlines()[-2:] == [
        f'    organismSinglePick (organismSinglePick) = ["{_P01}"] (chosen by you)',
        f"    variation_sample_meta (variation_sample_meta) = {_NO_CLAUSE} (chosen by you)",
    ]


def test_an_answer_shows_the_value_its_option_sets_as_stated() -> None:
    question = OpenQuestion(
        question="Which organism?",
        options=[
            TypedOption(
                id=label,
                label=label,
                binding=SetValues(
                    criterion_id="c_snps", params={"organismSinglePick": entry}
                ),
            )
            for label, entry in (("falciparum", _PF), ("vivax", _P01))
        ],
    )
    answer = UserQuestionAnswer(
        question_id="q1", prompt="Which organism?", chosen_labels=["falciparum"]
    )

    shown = answers_text([answer], [question], _spec())

    assert (
        shown
        == f'"Which organism?" -> falciparum (sets organismSinglePick to ["{_PF}"])'
    )
