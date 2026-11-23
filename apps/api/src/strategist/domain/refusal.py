from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)
from veupathdb.model import CamelModel

_WHITESPACE = re.compile(r"\s+")


def _one_line(value: object) -> object:
    match value:
        case str():
            return _WHITESPACE.sub(" ", value).strip()
        case _:
            return value


type Closing = Literal[
    "Nothing was recorded.", "Nothing was written.", "Nothing was read."
]

Sentence = Annotated[str, BeforeValidator(_one_line), StringConstraints(min_length=1)]


class Check(StrEnum):
    AN_ABSENCE_TO_A_READ = "an_absence_to_a_read"
    AN_OPTION_TO_A_HELD_EXPRESSION = "an_option_to_a_held_expression"
    AN_OPTION_TO_ITS_PARAMETER = "an_option_to_its_parameter"
    AN_ORGANISM_TO_A_STEP = "an_organism_to_a_step"
    ANSWERS = "answers"
    ARGUMENTS = "arguments"
    BOUND_ANALYSIS = "bound_analysis"
    COMPUTED_GROUPS = "computed_groups"
    COUNT = "count"
    DEPENDENT = "dependent"
    DROP = "drop"
    EDA_WAIT = "eda_wait"
    EXPRESSION = "expression"
    GENE_IDS = "gene_ids"
    GENE_SET = "gene_set"
    IN_PLACE = "in_place"
    LABELS = "labels"
    LOOKUP = "lookup"
    OBSOLETE_PICK = "obsolete_pick"
    OFF_TOPIC_ESSAY = "off_topic_essay"
    OPEN_VALUE_IN_PROSE = "open_value_in_prose"
    ORGANISM_CARRIED = "organism_carried"
    ORGANISM_NAMED = "organism_named"
    PHRASE = "phrase"
    PHYLETIC = "phyletic"
    PROPOSAL_PLAN = "proposal_plan"
    PROPOSAL_SEARCH = "proposal_search"
    PROPOSAL_SHAPE = "proposal_shape"
    PROPOSAL_TITLE = "proposal_title"
    RADIO = "radio"
    READING = "reading"
    REQUIRED = "required"
    REQUIREMENTS = "requirements"
    RESOLVE = "resolve"
    ROLE = "role"
    SAME_NAMED_SUBSET = "same_named_subset"
    SAVED_STRATEGY = "saved_strategy"
    SEARCH = "search"
    SOURCES = "sources"
    STATED_VALUE = "stated_value"
    THE_DIGEST_TO_THE_EVIDENCE = "the_digest_to_the_evidence"
    THE_INTERSECT_TO_ITS_ORGANISMS = "the_intersect_to_its_organisms"
    THE_JOIN_TO_THE_SPEC = "the_join_to_the_spec"
    THE_QUESTIONS_TO_A_DIMENSION = "the_questions_to_a_dimension"
    THE_QUESTIONS_TO_THE_DRAFT = "the_questions_to_the_draft"
    THE_READINGS_TO_THE_SITE = "the_readings_to_the_site"
    THE_REPORTS_TO_THE_REFUSALS = "the_reports_to_the_refusals"
    THE_REPORTS_TO_THE_REQUIREMENT_LIST = "the_reports_to_the_requirement_list"
    THE_ROUTE_TO_ANOTHER_SITE = "the_route_to_another_site"
    THE_SLOT_TO_ITS_STEP = "the_slot_to_its_step"
    THE_STRUCTURE_TO_BOUND_CRITERIA = "the_structure_to_bound_criteria"
    THE_SUBTREE_TO_THE_SPEC = "the_subtree_to_the_spec"
    THE_TAXA_TO_THEIR_SCOPE = "the_taxa_to_their_scope"
    THE_TREE_TO_ITS_READ_BACK = "the_tree_to_its_read_back"
    THE_TREE_TO_ITS_RECORD_CLASSES = "the_tree_to_its_record_classes"
    THE_VALUE_TO_THE_SPEC = "the_value_to_the_spec"
    UNBUILT_EDA_CRITERION = "unbuilt_eda_criterion"
    UNDECIDED = "undecided"
    UNFOLLOWED_REACH = "unfollowed_reach"
    UNKNOWN_NAMES = "unknown_names"
    UNLISTED_SEARCH = "unlisted_search"
    UNMET_REQUIREMENT = "unmet_requirement"
    UNSAVED_CONTROLS = "unsaved_controls"
    UNSERVED = "unserved"
    UNVERIFIED_BUILD = "unverified_build"
    UPLOAD = "upload"
    VALIDATION = "validation"
    VARIANT_PARAMETERS = "variant_parameters"
    WAITING = "waiting"
    WHY = "why"


class RefusalKey(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Annotated[str, StringConstraints(min_length=1)]
    criterion: str = ""
    search: str = ""
    parameter: str = ""

    def label(self) -> str:
        named = [part for part in (self.criterion, self.search, self.parameter) if part]
        return " / ".join(named) if named else self.check

    def __hash__(self) -> int:
        return hash((self.check, self.criterion, self.search, self.parameter))

    def clears(self, key: RefusalKey, *, by: str) -> bool:
        if by != self.check:
            return False
        return key.check == Check.ARGUMENTS or (key.criterion, key.search) == (
            self.criterion,
            self.search,
        )

    def under(self, *, criterion: str, search: str) -> RefusalKey:
        return self.model_copy(
            update={
                "criterion": self.criterion or criterion,
                "search": self.search or search,
            }
        )


class Problem(CamelModel):
    model_config = ConfigDict(frozen=True)

    key: RefusalKey
    sentence: Sentence

    def __hash__(self) -> int:
        return hash((self.key, self.sentence))


class Problems(CamelModel):
    model_config = ConfigDict(frozen=True)

    found: tuple[Problem, ...] = ()

    @field_validator("found", mode="after")
    @classmethod
    def _named_once(cls, found: tuple[Problem, ...]) -> tuple[Problem, ...]:
        return tuple(dict.fromkeys(found))

    @classmethod
    def one(cls, key: RefusalKey, sentence: str) -> Problems:
        return cls(found=(Problem(key=key, sentence=sentence),))

    def plus(self, more: Problems) -> Problems:
        return Problems(found=self.found + more.found)

    def under(self, *, criterion: str, search: str) -> Problems:
        return Problems(
            found=tuple(
                Problem(
                    key=p.key.under(criterion=criterion, search=search),
                    sentence=p.sentence,
                )
                for p in self.found
            )
        )

    @property
    def empty(self) -> bool:
        return not self.found

    def keys(self) -> tuple[RefusalKey, ...]:
        return tuple(dict.fromkeys(p.key for p in self.found))

    def text(self) -> str:
        if not self.found:
            return ""
        if len(self.found) == 1:
            return self.found[0].sentence
        lines = [f"{i}. {p.sentence}" for i, p in enumerate(self.found, start=1)]
        return "\n".join([f"{len(self.found)} problems:", *lines])


class KeyUse(CamelModel):
    model_config = ConfigDict(frozen=True)

    key: RefusalKey
    used: Annotated[int, Field(ge=1)]
    by: str = ""


class RefusalLedger(CamelModel):
    model_config = ConfigDict(frozen=True)

    uses: tuple[KeyUse, ...] = ()

    @field_validator("uses", mode="after")
    @classmethod
    def _one_row_per_key(cls, uses: tuple[KeyUse, ...]) -> tuple[KeyUse, ...]:
        if len({use.key for use in uses}) != len(uses):
            msg = "a refusal ledger holds one row per key"
            raise ValueError(msg)
        return uses

    def used(self, key: RefusalKey) -> int:
        return next((use.used for use in self.uses if use.key == key), 0)

    def charge(self, problems: Problems, per_key: int, *, by: str = "") -> Charge:
        named = problems.keys()
        live = tuple(key for key in named if self.used(key) < per_key)
        raised = tuple(
            use.model_copy(update={"used": use.used + 1}) if use.key in live else use
            for use in self.uses
        )
        first = tuple(
            KeyUse(key=key, used=1, by=by) for key in live if self.used(key) == 0
        )
        return Charge(
            ledger=RefusalLedger(uses=raised + first),
            refused=Problems(found=tuple(p for p in problems.found if p.key in live)),
            spent=Problems(found=tuple(p for p in problems.found if p.key not in live)),
        )

    def cleared(self, on: RefusalKey) -> RefusalLedger:
        return RefusalLedger(
            uses=tuple(use for use in self.uses if not on.clears(use.key, by=use.by))
        )


class Charge(CamelModel):
    model_config = ConfigDict(frozen=True)

    ledger: RefusalLedger
    refused: Problems
    spent: Problems
