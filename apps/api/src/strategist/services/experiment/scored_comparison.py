"""Scored variant comparison (Phase 2b): run a full experiment per variant
against positive/negative control gene lists, then rank the variants by an
objective metric (MCC by default) and name a winner.

This is the controls-based counterpart to the no-controls exploratory
``variant_comparison`` - here every variant gets real classification metrics
(sensitivity, precision, MCC, ...) so there's an objective "best".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field, ValidationError
from veupathdb.errors import WDKError
from veupathdb_mcp.controls import CONTROLS_PARAM, CONTROLS_SEARCH
from veupathdb_mcp.wdk import extract_record_ids

from strategist.domain.unread import Unread
from strategist.services.experiment.service import run_experiment
from strategist.services.experiment.types.experiment import (
    Experiment,
    ExperimentConfig,
)
from strategist.services.experiment.variant_comparison import (
    VariantSpec,
    run_variant_search,
)
from strategist.services.site_errors import site_words

_MAX_ERROR_CHARS = 200


class ScoredVariant(CamelModel):
    label: str
    search_name: str
    experiment_id: str | None = None
    mcc: float | Unread | None = None
    balanced_accuracy: float | Unread | None = None
    f1: float | Unread | None = None
    sensitivity: float | Unread | None = None
    precision: float | Unread | None = None
    error: str | None = None
    control_hits: list[str] | Unread = Field(default_factory=list)
    """The given control ids this variant's result contains, in the given order,
    or why the result was not read."""


class ScoredComparison(CamelModel):
    variants: list[ScoredVariant]
    winner_label: str | None
    objective: str
    """The metric the variants were ranked by."""


type Objective = Literal["mcc", "balanced_accuracy", "f1", "precision", "sensitivity"]

RANK_BY: dict[Objective, Callable[[ScoredVariant], float | Unread | None]] = {
    "mcc": lambda v: v.mcc,
    "balanced_accuracy": lambda v: v.balanced_accuracy,
    "f1": lambda v: v.f1,
    "precision": lambda v: v.precision,
    "sensitivity": lambda v: v.sensitivity,
}


def _one_line(text: str) -> str:
    """One short sentence, whatever the source wrote."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= _MAX_ERROR_CHARS:
        return collapsed
    return collapsed[: _MAX_ERROR_CHARS - 3] + "..."


def _first_field_error(exc: ValidationError) -> str:
    """The first rejected field and why, never the whole validation dump."""
    errors = exc.errors()
    if not errors:
        return _one_line(str(exc))
    first = errors[0]
    location = ".".join(str(part) for part in first["loc"])
    message = first["msg"] if not location else f"{location}: {first['msg']}"
    if len(errors) == 1:
        return _one_line(message)
    return _one_line(f"{message} (and {len(errors) - 1} more)")


async def _hits_from_search(
    spec: VariantSpec, *, site_id: str, control_ids: list[str]
) -> list[str] | Unread:
    """The control ids in this variant's result, read without scoring it."""
    if not control_ids:
        return []
    try:
        answer = await run_variant_search(site_id, spec)
    except (WDKError, httpx.HTTPError) as exc:
        return Unread(reason=site_words(exc))
    found = set(extract_record_ids(answer.records))
    return [gene for gene in control_ids if gene in found]


async def _failed_variant(
    spec: VariantSpec,
    *,
    site_id: str,
    control_ids: list[str],
    error: str,
) -> ScoredVariant:
    return ScoredVariant(
        label=spec.label,
        search_name=spec.search_name,
        error=error,
        control_hits=await _hits_from_search(
            spec, site_id=site_id, control_ids=control_ids
        ),
    )


def _hits_from_experiment(exp: Experiment, control_ids: list[str]) -> list[str]:
    found = exp.result_gene_ids()
    return [gene for gene in control_ids if gene in found]


async def _score_one(
    spec: VariantSpec,
    *,
    site_id: str,
    user_id: str | None,
    positive_controls: list[str],
    negative_controls: list[str],
    control_ids: list[str],
) -> ScoredVariant:
    config = ExperimentConfig(
        site_id=site_id,
        record_type=spec.record_type,
        search_name=spec.search_name,
        parameters=spec.parameters,
        positive_controls=positive_controls,
        negative_controls=negative_controls,
        controls_search_name=CONTROLS_SEARCH,
        controls_param_name=CONTROLS_PARAM,
        name=spec.label,
    )
    try:
        exp = await run_experiment(config, user_id=user_id)
    except ValidationError as exc:
        return await _failed_variant(
            spec,
            site_id=site_id,
            control_ids=control_ids,
            error=_first_field_error(exc),
        )
    except (WDKError, ValueError) as exc:
        return await _failed_variant(
            spec,
            site_id=site_id,
            control_ids=control_ids,
            error=_one_line(str(exc)),
        )
    hits = _hits_from_experiment(exp, control_ids)
    if exp.status == "error" or exp.metrics is None:
        return ScoredVariant(
            label=spec.label,
            search_name=spec.search_name,
            experiment_id=exp.id,
            error=_one_line(exp.error or "experiment produced no metrics"),
            control_hits=hits,
        )
    m = exp.metrics
    return ScoredVariant(
        label=spec.label,
        search_name=spec.search_name,
        experiment_id=exp.id,
        mcc=m.mcc,
        balanced_accuracy=m.balanced_accuracy,
        f1=m.f1_score,
        sensitivity=m.sensitivity,
        precision=m.precision,
        control_hits=hits,
    )


async def run_scored_comparison(
    site_id: str,
    user_id: str | None,
    variants: list[VariantSpec],
    *,
    positive_controls: list[str],
    negative_controls: list[str],
    objective: Objective = "mcc",
) -> ScoredComparison:
    """Run each variant as a scored experiment and rank by *objective*.

    Variants run sequentially (each is a full WDK experiment). A failed
    variant carries one line saying why and is excluded from ranking; it still
    reports which of the control ids its result contains.
    """
    control_ids = list(dict.fromkeys([*positive_controls, *negative_controls]))
    scored = [
        await _score_one(
            v,
            site_id=site_id,
            user_id=user_id,
            positive_controls=positive_controls,
            negative_controls=negative_controls,
            control_ids=control_ids,
        )
        for v in variants
    ]
    ranking = ranked_winner(scored, objective)
    return ScoredComparison(
        variants=scored,
        winner_label=None if ranking.winner is None else ranking.winner.label,
        objective=ranking.metric,
    )


@dataclass(frozen=True)
class Ranking:
    """The metric the variants rank by, the variant it puts first and its
    score, and why the asked objective was not measured when it was not."""

    metric: Objective
    winner: ScoredVariant | None = None
    score: float | None = None
    unmeasured: Unread | None = None


def _measured(
    variants: list[ScoredVariant], objective: Objective
) -> tuple[list[tuple[float, ScoredVariant]], Unread | None]:
    found: list[tuple[float, ScoredVariant]] = []
    unread: Unread | None = None
    for variant in variants:
        if variant.error is not None:
            continue
        match RANK_BY[objective](variant):
            case Unread() as why:
                unread = unread or why
            case None:
                pass
            case score:
                found.append((score, variant))
    return found, unread


def ranked_winner(variants: list[ScoredVariant], objective: Objective) -> Ranking:
    """A variant ranks by the objective where it is measured, else by recall,
    else no variant wins."""
    asked, unmeasured = _measured(variants, objective)
    if asked:
        score, winner = max(asked, key=lambda pair: pair[0])
        return Ranking(metric=objective, winner=winner, score=score)
    recall, _ = _measured(variants, "sensitivity")
    if recall:
        score, winner = max(recall, key=lambda pair: pair[0])
        return Ranking(
            metric="sensitivity", winner=winner, score=score, unmeasured=unmeasured
        )
    return Ranking(metric=objective, unmeasured=unmeasured)
