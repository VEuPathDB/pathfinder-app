"""The row of an exported analysis step: the values its compute ran with, each
with who set it, and the counts the compute holds for each chosen cut."""

from __future__ import annotations

from collections.abc import Sequence

from veupathdb.domain.parameters import NumberValue, ParamValue, StringValue

from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.domain.log2_scale import fold_label
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding, CutTallies
from pathfinder.domain.strategy.value_binding import plain_value
from pathfinder.domain.strategy.value_source import value_source
from pathfinder.domain.turn_facts import ParameterFact
from pathfinder.services.eda.direction import direction_sentence

# A value no statistic of the compute counts at another reading.
_ANALYSIS_UNMEASURED = "its count at another value is not measured"


def _text(text: str | None) -> ParamValue | None:
    return StringValue(value=text) if text else None


def _number(number: float | None) -> ParamValue | None:
    return None if number is None else NumberValue(value=number)


def _direction_label(binding: AnalysisBinding) -> str:
    """The genes the compute's direction keeps, named by its groups."""
    if binding.comparison is None or binding.effect_direction is None:
        return ""
    return direction_sentence(binding.comparison, binding.effect_direction)


def _analysis_values(
    binding: AnalysisBinding,
) -> list[tuple[str, str, ParamValue, str]]:
    """Each value the compute ran with: its name, its display name, its value
    and the label that reads it."""
    groups = binding.comparison or EdaComparison(group_a=[], group_b=[])
    effect_size = binding.effect_size_label or "Effect size threshold"
    rows = [
        ("group_a", "Reference group", _text(", ".join(groups.group_a)), ""),
        ("group_b", "Compared group", _text(", ".join(groups.group_b)), ""),
        ("method", "Method", _text(binding.method), ""),
        (
            "value_variable",
            "Measured variable",
            _text(binding.value_variable),
            binding.value_variable_name,
        ),
        (
            "effect_direction",
            "Effect direction",
            _text(binding.effect_direction),
            _direction_label(binding),
        ),
        (
            "effect_size_threshold",
            effect_size,
            _number(binding.effect_size_threshold),
            ""
            if binding.effect_size_threshold is None
            else fold_label(effect_size, f"{binding.effect_size_threshold:g}"),
        ),
        (
            "significance_threshold",
            "Significance threshold",
            _number(binding.significance_threshold),
            "",
        ),
        ("subset", "Subset", _text(", ".join(binding.subset_as_shown())), ""),
    ]
    return [(name, shown, v, label) for name, shown, v, label in rows if v is not None]


def _records(count: int, noun: str) -> str:
    return f"{count:,} {noun}" if count == 1 else f"{count:,} {noun}s"


def _cut_note(name: str, at: str, tallies: CutTallies | None, noun: str) -> str | None:
    """The count at a chosen cut beside the count at its other reading, or None
    when no statistic of the compute counts it. ``at`` names the chosen value."""
    if tallies is None:
        return None
    kept = _records(tallies.retained, noun)
    match name:
        case "effect_size_threshold":
            return (
                f"{at}: {tallies.retained:,} of {_records(tallies.tested, noun)} "
                f"tested; at 0: {tallies.at_any_effect:,}"
            )
        case "significance_threshold":
            return f"{at}: {kept}; at 1: {tallies.at_any_significance:,}"
        case "effect_direction":
            return (
                f"{at}: {kept}; {tallies.retained_up:,} higher in the compared "
                f"group, {tallies.retained_down:,} higher in the reference group"
            )
        case _:
            return None


def analysis_parameters(
    binding: AnalysisBinding, said: Sequence[str], noun: str
) -> list[ParameterFact]:
    """The compute's values, each stated when a researcher message holds it on
    the scale the researcher wrote it. A value the researcher did not state
    shows the counts the compute holds for it, where it holds any."""
    facts: list[ParameterFact] = []
    for name, shown, value, label in _analysis_values(binding):
        source = value_source(
            value,
            placeholder=False,
            unset=False,
            request_texts=said,
            display_name=shown,
        )
        written = plain_value(value)
        note = _cut_note(
            name, f"{shown} at the chosen {written}", binding.tallies, noun
        )
        facts.append(
            ParameterFact(
                name=name,
                display_name=shown,
                value=written,
                label=label,
                source=source,
                notes=[]
                if source == "stated"
                else [_ANALYSIS_UNMEASURED if note is None else note],
            )
        )
    return facts


__all__ = ["analysis_parameters"]
