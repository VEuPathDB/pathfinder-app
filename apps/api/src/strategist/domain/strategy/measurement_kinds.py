from __future__ import annotations

from typing import Literal

CountedKind = Literal[
    "loosest_bound",
    "wildcard_phrase",
    "phrase_reading",
    "words_reading",
    "site_search_reach",
    "any_strain",
    "all_strains",
    "site_default",
    "bound_count",
    "reading",
]
MeasurementKind = Literal[
    CountedKind,
    "vocabulary_label",
    "options_not_taken",
    "not_measurable",
    "picked_from_a_cut_list",
    "picked_from_a_lookup",
    "label_without_the_concept",
]

TAKEN_FROM_A_READ = frozenset({"picked_from_a_cut_list", "picked_from_a_lookup"})
