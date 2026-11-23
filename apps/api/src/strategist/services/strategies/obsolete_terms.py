"""The picks whose site label marks the term obsolete, read from the labels a
bind already holds."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import SHOWN_CANDIDATES, rank_entries
from veupathdb_mcp.catalog import ParameterInfo

from strategist.domain.strategy.operational_spec import Measurement
from strategist.domain.strategy.value_label import label_term
from strategist.domain.strategy.words import words_of

# The first word an ontology writes in the name of a term it retired.
OBSOLETE = "obsolete"


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


def says_obsolete(value: str, display: str) -> bool:
    return words_of(label_term(value, display))[:1] == [OBSOLETE]


def _without_the_word(label: str) -> str:
    return " ".join(w for w in label.split() if w.casefold() != OBSOLETE)


def obsolete_picks(
    labels: Sequence[Measurement], infos: Sequence[ParameterInfo]
) -> list[ObsoletePick]:
    """Each labelled pick whose label says obsolete, with the vocabulary's
    current entries nearest the rest of its label."""
    by_name = {info.name: info for info in infos}
    found: list[ObsoletePick] = []
    for m in labels:
        info = by_name.get(m.param)
        if (
            m.kind != "vocabulary_label"
            or info is None
            or not says_obsolete(m.reading, m.label)
        ):
            continue
        current = [
            o for o in info.vocabulary() if not says_obsolete(o.value, o.display)
        ]
        found.append(
            ObsoletePick(
                param=m.param,
                term=m.reading,
                label=m.label,
                nearest=[
                    o.display
                    for o in rank_entries(
                        current, _without_the_word(m.label), SHOWN_CANDIDATES
                    )
                ],
            )
        )
    return found


__all__ = ["OBSOLETE", "ObsoletePick", "obsolete_picks", "says_obsolete"]
