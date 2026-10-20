from __future__ import annotations

from dataclasses import dataclass, field

from veupathdb.eda import EdaDistributionResponse

_BINS_SHOWN = 40
_CATEGORICAL = "categorical"


@dataclass(frozen=True)
class HistogramCut:
    labels: list[str] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    total: int = 0
    note: str | None = None


def _count(value: float) -> str:
    return f"{value:,.0f}"


def _spread(values: list[float]) -> str:
    low, high = min(values), max(values)
    if low == high:
        return f"Every bin holds {_count(low)}."
    return f"Bins hold between {_count(low)} and {_count(high)} each."


def cut_histogram(
    distribution: EdaDistributionResponse | None, *, data_shape: str | None
) -> HistogramCut:
    if distribution is None:
        return HistogramCut()
    bins = [(bin_.bin_label, bin_.value) for bin_ in distribution.histogram]
    if len(bins) <= _BINS_SHOWN:
        return HistogramCut(
            labels=[label for label, _ in bins],
            values=[value for _, value in bins],
            total=len(bins),
        )
    largest = data_shape == _CATEGORICAL
    ranked = sorted(bins, key=lambda bin_: -bin_[1]) if largest else bins
    shown = ranked[:_BINS_SHOWN]
    values = [value for _, value in bins]
    held = sum(value for _, value in shown)
    counted = sum(values)
    which = (
        f"the {_BINS_SHOWN} largest" if largest else f"the first {_BINS_SHOWN} in order"
    )
    share = held / counted if counted else 0.0
    note = (
        f"{len(bins):,} bins in all; {which} are shown here, holding "
        f"{_count(held)} of {_count(counted)} counted values ({share:.1%}). "
        f"{_spread(values)} The figure shows every bin."
    )
    return HistogramCut(
        labels=[label for label, _ in shown],
        values=[value for _, value in shown],
        total=len(bins),
        note=note,
    )
