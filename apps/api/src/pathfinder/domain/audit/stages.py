"""The four stages of an audit run, which one a resumed run starts from, its requests, and why it halted."""

from __future__ import annotations

from typing import Literal, Self

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, model_validator

from pathfinder.domain.statistic_facts import Sentence

StageName = Literal["collect", "screen", "confirm", "tie_break"]
RunStatus = Literal["planned", "running", "finished"]
STAGES: tuple[StageName, ...] = ("collect", "screen", "confirm", "tie_break")
SIGN_IN_NEEDED = "sign-in needed"
HaltKind = Literal["sign_in", "task_failed"]


class RunHalt(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: HaltKind
    detail: Sentence


class StageRecord(CamelModel):
    model_config = ConfigDict(frozen=True)

    name: StageName
    finished: bool = False
    requests: int = Field(default=0, ge=0)
    store_reads: int = Field(default=0, ge=0)
    done: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    message: Sentence = ""


def _fresh() -> tuple[StageRecord, ...]:
    return tuple(StageRecord(name=name) for name in STAGES)


class RunStages(CamelModel):
    model_config = ConfigDict(frozen=True)

    stages: tuple[StageRecord, ...] = Field(default_factory=_fresh)
    halted: Sentence | None = None
    target_failure: Sentence | None = None

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        if tuple(stage.name for stage in self.stages) != STAGES:
            msg = f"a run holds the stages {list(STAGES)} in that order"
            raise ValueError(msg)
        done = [stage.finished for stage in self.stages]
        if done != sorted(done, reverse=True):
            msg = "a stage finishes only after the stages before it"
            raise ValueError(msg)
        return self

    @property
    def next_stage(self) -> StageName | None:
        return next((stage.name for stage in self.stages if not stage.finished), None)

    @property
    def unfinished(self) -> tuple[StageName, ...]:
        return tuple(stage.name for stage in self.stages if not stage.finished)

    @property
    def requests(self) -> int:
        return sum(stage.requests for stage in self.stages)

    @property
    def store_reads(self) -> int:
        return sum(stage.store_reads for stage in self.stages)

    @property
    def halt_reason(self) -> RunHalt | None:
        if self.halted is None:
            return None
        kind: HaltKind = "sign_in" if self.halted == SIGN_IN_NEEDED else "task_failed"
        return RunHalt(kind=kind, detail=self.halted)

    def _with(self, **update: object) -> RunStages:
        return RunStages.model_validate({**dict(self), **update})

    def _changed(self, name: StageName, **update: object) -> RunStages:
        return self._with(
            stages=tuple(
                s.model_copy(update=update) if s.name == name else s
                for s in self.stages
            )
        )

    def count(self, name: StageName, requests: int, store_reads: int = 0) -> RunStages:
        record = next(s for s in self.stages if s.name == name)
        return self._changed(
            name,
            requests=record.requests + requests,
            store_reads=record.store_reads + store_reads,
        )

    def progress(
        self, name: StageName, *, done: int, total: int, message: str
    ) -> RunStages:
        return self._changed(name, done=done, total=total, message=message)

    def finish(self, name: StageName) -> RunStages:
        if name != self.next_stage:
            msg = f"{name} is not the next stage; {self.next_stage} is"
            raise ValueError(msg)
        return self._changed(name, finished=True)

    def reopen(self, name: StageName) -> RunStages:
        first = STAGES.index(name)
        return self._with(
            stages=tuple(
                s.model_copy(update={"finished": s.finished and k < first})
                for k, s in enumerate(self.stages)
            )
        )

    def halt(self, reason: str | None) -> RunStages:
        return self._with(halted=reason)

    def note_target_failure(self, message: str) -> RunStages:
        return self._with(target_failure=message)
