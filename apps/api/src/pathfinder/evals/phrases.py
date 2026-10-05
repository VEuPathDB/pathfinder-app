"""The phrases a case holds a run's replies to, and the text each check reads."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pathfinder.evals.case import ExpectedOutcome
from pathfinder.evals.difference import CaseDifference

_SPACING = re.compile(r"[\s-]+")
# A phrase whose right wordings differ joins them with this mark.
_OR = " | "
# A phrase a reply must carry counts where the facts part shows it; a phrase it
# must omit is a claim of the prose, so the facts part is not read.
_MENTIONS_READ = "the facts part and the reply"
_OMITS_READ = "the reply"


def shown(facts: str, reply: str) -> str:
    """What a turn showed the researcher: its facts part's lines, then its reply."""
    return "\n".join([*([facts] if facts else []), reply])


@dataclass(frozen=True)
class PhraseTexts:
    """The last turn's reply and facts part, and each turn's, in turn order."""

    reply: str
    facts: str
    turn_replies: list[str]
    turn_facts: list[str]

    def turn(self, index: int, *, omits: bool) -> str:
        """The text a per-turn check reads; an unreached turn reads empty."""
        replies, facts = self.turn_replies, self.turn_facts
        reply = replies[index] if index < len(replies) else ""
        if omits:
            return reply
        return shown(facts[index] if index < len(facts) else "", reply)


def _phrase_form(text: str) -> str:
    """Text as a phrase is matched: no case, a hyphen reads as a space, one space."""
    return _SPACING.sub(" ", text.casefold())


def _shows(phrase: str, read: str) -> bool:
    """Whether the read text holds the phrase, or any wording it joins with ``_OR``."""
    return any(_phrase_form(wording) in read for wording in phrase.split(_OR))


def _phrase_check(
    field: str, phrases: list[str], text: str, *, omits: bool
) -> list[CaseDifference]:
    """The phrases *text* lacks, or holds when *omits*, as one difference."""
    read = _phrase_form(text)
    wrong = [p for p in phrases if _shows(p, read) == omits]
    if not wrong:
        return []
    return [
        CaseDifference(
            field=field,
            expected=", ".join(wrong),
            actual=text[:200],
            read=_OMITS_READ if omits else _MENTIONS_READ,
        )
    ]


def phrase_differences(
    expected: ExpectedOutcome, texts: PhraseTexts
) -> list[CaseDifference]:
    """Every phrase the replies lack or hold against the case's expectation."""
    differences = [
        *_phrase_check(
            "replyMentions",
            expected.reply_mentions,
            shown(texts.facts, texts.reply),
            omits=False,
        ),
        *_phrase_check("replyOmits", expected.reply_omits, texts.reply, omits=True),
    ]
    by_turn = (
        ("turnReplyMentions", expected.turn_reply_mentions, False),
        ("turnReplyOmits", expected.turn_reply_omits, True),
    )
    for field, phrases_of, omits in by_turn:
        for turn, phrases in sorted(phrases_of.items()):
            differences.extend(
                _phrase_check(
                    f"{field}.{turn}",
                    phrases,
                    texts.turn(turn, omits=omits),
                    omits=omits,
                ),
            )
    return differences


__all__ = ["PhraseTexts", "phrase_differences", "shown"]
