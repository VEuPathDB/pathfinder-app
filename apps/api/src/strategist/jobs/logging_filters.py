"""Keep task arguments and task results out of every procrastinate log record."""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

_PROCRASTINATE = "procrastinate"
_RESULT_MARK = " - Result: "


class _LoggedJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    task_name: str = ""
    queue: str | None = None
    status: str | None = None
    call_string: str = ""

    @property
    def label(self) -> str:
        return f"{self.task_name}[{self.id}]"

    def kept(self) -> dict[str, object]:
        return self.model_dump(include={"id", "task_name", "queue", "status"})


class _JobRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    job: _LoggedJob | None = None
    jobs: list[_LoggedJob] = Field(default_factory=list)


class TaskArgumentsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != _PROCRASTINATE and not record.name.startswith(
            f"{_PROCRASTINATE}.",
        ):
            return True
        logged = _JobRecord.model_validate(record.__dict__)
        named = [job for job in (logged.job, *logged.jobs) if job is not None]
        message = record.getMessage()
        for job in named:
            if job.call_string:
                message = message.replace(job.call_string, job.label)
        record.msg = message.partition(_RESULT_MARK)[0]
        record.args = ()
        record.__dict__.pop("result", None)
        if logged.job is not None:
            record.__dict__["job"] = logged.job.kept()
        if "jobs" in record.__dict__:
            record.__dict__["jobs"] = [job.kept() for job in logged.jobs]
        return True


def install_procrastinate_redaction() -> None:
    scrub = TaskArgumentsFilter()
    names = {_PROCRASTINATE} | {
        name
        for name in logging.Logger.manager.loggerDict
        if name.startswith(f"{_PROCRASTINATE}.")
    }
    targets: list[logging.Filterer] = [logging.getLogger(name) for name in names]
    targets.extend(logging.getLogger().handlers)
    for target in targets:
        if not any(isinstance(f, TaskArgumentsFilter) for f in target.filters):
            target.addFilter(scrub)


__all__ = ["TaskArgumentsFilter", "install_procrastinate_redaction"]
