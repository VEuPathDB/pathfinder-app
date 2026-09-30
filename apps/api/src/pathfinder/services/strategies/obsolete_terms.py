"""The picks whose site label marks the term obsolete, read from the labels a
bind already holds."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import MAX_NEAREST_ENTRIES, nearest_entries
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.operational_spec import Measurement

# The word an ontology writes in the label of a term it retired.
_OBSOLETE = "obsolete"


class ObsoletePick(BaseModel):
    """A pick the site labels obsolete, and the current entries nearest its words."""

    model_config = ConfigDict(frozen=True)

    param: str
    term: str
    label: str
    nearest: list[str]

    def refusal(
        self, search_name: str, display_name: str, *, counted: str, researchers: bool
    ) -> str:
        """The refusal of a bind that holds this pick and counts nothing.

        ``counted`` is the count the site answered, with its noun. A term the
        researcher set is replaced only by their answer to a card.
        """
        held = (
            f"{self.param} ({display_name}) on {search_name} holds {self.term!r}, "
            f"which the site labels {self.label!r}: the ontology marks the term "
            f"obsolete, and the site counts {counted} for it at these values. It "
            "is not bound."
        )
        if researchers:
            return (
                f"{held} The researcher named this term, so ask them with a card "
                "which entry to use; the current entries nearest its words are "
                f"{self.nearest}."
            )
        return (
            f"{held} Pass a current entry, such as one of {self.nearest}, or ask "
            "the researcher which one they mean."
        )


def _says_obsolete(label: str) -> bool:
    return _OBSOLETE in re.findall(r"[a-z]+", label.casefold())


def _without_the_word(label: str) -> str:
    return " ".join(w for w in label.split() if w.casefold() != _OBSOLETE)


def obsolete_picks(
    labels: Sequence[Measurement], infos: Sequence[ParameterInfo]
) -> list[ObsoletePick]:
    """Each labelled pick whose label says obsolete, with the vocabulary's
    current entries nearest the rest of its label."""
    by_name = {info.name: info for info in infos}
    found: list[ObsoletePick] = []
    for m in labels:
        info = by_name.get(m.param)
        if m.kind != "vocabulary_label" or info is None or not _says_obsolete(m.label):
            continue
        current = [o for o in info.vocabulary() if not _says_obsolete(o.display)]
        near = set(
            nearest_entries(current, _without_the_word(m.label), MAX_NEAREST_ENTRIES)
        )
        found.append(
            ObsoletePick(
                param=m.param,
                term=m.reading,
                label=m.label,
                nearest=[o.display for o in current if {o.value, o.display} & near],
            )
        )
    return found


__all__ = ["ObsoletePick", "obsolete_picks"]
