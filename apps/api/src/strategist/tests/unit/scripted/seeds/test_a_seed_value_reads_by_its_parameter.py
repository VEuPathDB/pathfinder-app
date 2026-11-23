"""Every seed value a recorded definition declares reads by its parameter's rule,
and every plasmodb seed value names an entry of the plasmodb recording."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    StatedValuesError,
    VocabularyEntryError,
    read_stated_values,
)
from veupathdb.domain.strategy import walk

from strategist.tests._support.record_classes import recorded_searches
from strategist_scripted.seeds.catalog import (
    get_seeds_for_site,
    seed_databases,
)

_RECORDED_SITE = "plasmodb"


def _faults() -> list[str]:
    recorded = recorded_searches()
    faults: list[str] = []
    for site_id in seed_databases():
        for seed in get_seeds_for_site(site_id):
            for node in walk(seed.step_node()):
                search = recorded.get(node.search_name)
                if search is None:
                    continue
                stated = {n: v.to_decoded() for n, v in node.parameters.items()}
                try:
                    read_stated_values(search.parameters or [], stated)
                except StatedValuesError as refused:
                    faults.extend(
                        f"{site_id} {seed.name}: {f.text}" for f in refused.faults
                    )
                except VocabularyEntryError as refused:
                    if site_id == _RECORDED_SITE:
                        faults.append(f"{site_id} {seed.name}: {refused.detail}")
    return faults


def test_every_recorded_seed_value_reads_natively() -> None:
    assert _faults() == []
