"""A run checks a fixed-size sample of its candidates, the same sample for one seed."""

from __future__ import annotations

from collections import Counter

import pytest

from pathfinder.domain.audit.sampling import sample_candidates, sampled
from pathfinder.domain.audit.scope import SingleGeneTarget
from pathfinder.domain.audit.screen import Candidate

KEYS = [f"gene_length:G{k}" for k in range(100)]


def test_every_key_is_kept_under_the_limit() -> None:
    assert sampled(KEYS[:3], 150, seed=7) == frozenset(KEYS[:3])


def test_a_sample_is_the_limit_and_the_same_for_one_seed() -> None:
    first = sampled(KEYS, 10, seed=7)
    assert len(first) == 10
    assert first <= frozenset(KEYS)
    assert sampled(list(reversed(KEYS)), 10, seed=7) == first
    assert sampled(KEYS, 10, seed=8) != first


def test_every_key_can_be_drawn() -> None:
    drawn = Counter(
        key for seed in range(64) for key in sampled(KEYS[:4], 2, seed=seed)
    )
    assert sorted(drawn) == sorted(KEYS[:4])


def test_each_genome_and_check_is_sampled_on_its_own() -> None:
    candidates = [
        Candidate(
            genome=genome,
            target=SingleGeneTarget(check="gene_length", genes=(f"{genome}_{k}",)),
        )
        for genome in ("A", "B")
        for k in range(5)
    ]
    chosen = sample_candidates(candidates, 2, seed=3)
    assert Counter(key.split(":")[1].split("_")[0] for key in chosen) == Counter(
        {"A": 2, "B": 2}
    )


def test_a_sample_holds_at_least_one_key() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        sampled(KEYS, 0, seed=1)
