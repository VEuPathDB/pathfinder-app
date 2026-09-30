"""The Lead's frame ledger names each bound value by the parameter's display
name, in readable form, with who set it and the measurements the bind read."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, StringValue

from pathfinder.ai.lead.ledger_render import render_frame_full
from pathfinder.ai.lead.ledger_sections import FrameSection
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)


def _section() -> FrameSection:
    return FrameSection(
        spec=OperationalSpec(
            goal="genes expressed in asexual blood stages",
            criteria=[
                Criterion(
                    id="c_expr",
                    text="expressed in asexual blood stages",
                    search_name="GenesByRNASeqPercentile",
                    resolved_params={
                        "min_expression_percentile": BoundValue(
                            value=StringValue(value="80"), source="default"
                        ),
                        "samples_percentile_generic": BoundValue(
                            value=MultiPickValue(values=["asexual blood stages"]),
                            source="stated",
                            basis="asexual blood stages",
                        ),
                    },
                    param_display_names={
                        "min_expression_percentile": "Minimum expression percentile",
                        "samples_percentile_generic": "Samples",
                    },
                    measurements=[
                        Measurement(
                            kind="loosest_bound",
                            param="min_expression_percentile",
                            count=5318,
                            reading="0",
                        )
                    ],
                    result_count=1087,
                )
            ],
        )
    )


def test_each_value_line_names_the_display_name_and_the_readable_value() -> None:
    lines = render_frame_full(_section()).splitlines()

    assert (
        "    Minimum expression percentile (min_expression_percentile) = 80 (default)"
        in lines
    )
    assert (
        "    Samples (samples_percentile_generic) = asexual blood stages (stated)"
        in lines
    )


def test_each_measurement_is_a_line_of_the_criterion() -> None:
    lines = render_frame_full(_section()).splitlines()

    assert (
        "    MEASURED Minimum expression percentile at the site's default of 80: "
        "1,087 genes; at 0: 5,318"
    ) in lines


def test_a_measurement_counts_in_the_noun_of_the_record_type() -> None:
    transcript = _section()
    assert transcript.spec is not None
    compound = FrameSection(
        spec=transcript.spec.model_copy(update={"record_type": "compound"})
    )

    measured = [
        [line for line in render_frame_full(s).splitlines() if "MEASURED" in line]
        for s in (transcript, compound)
    ]

    assert measured == [
        [
            (
                "    MEASURED Minimum expression percentile at the site's default "
                "of 80: 1,087 genes; at 0: 5,318"
            )
        ],
        [
            (
                "    MEASURED Minimum expression percentile at the site's default "
                "of 80: 1,087 compounds; at 0: 5,318"
            )
        ],
    ]
