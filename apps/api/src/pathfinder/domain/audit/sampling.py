"""Which screened candidates a run checks when it may check only some of them."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Sequence

from pathfinder.domain.audit.screen import Candidate


def _rank(seed: int, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()


def sampled(keys: Iterable[str], limit: int, seed: int) -> frozenset[str]:
    if limit < 1:
        msg = f"a sample holds at least 1 key, not {limit}"
        raise ValueError(msg)
    ordered = sorted(set(keys), key=lambda key: (_rank(seed, key), key))
    return frozenset(ordered[:limit])


def sample_candidates(
    candidates: Sequence[Candidate], limit: int, seed: int
) -> frozenset[str]:
    groups: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for candidate in candidates:
        groups[(candidate.genome, candidate.target.check)].append(candidate.target.key)
    return frozenset(
        key for keys in groups.values() for key in sampled(keys, limit, seed)
    )
