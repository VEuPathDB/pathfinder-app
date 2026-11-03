from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field, model_validator
from pydantic_ai import ModelRetry
from veupathdb.model import CamelModel
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.domain.strategy.operational_spec import RequirementLink
from pathfinder.domain.strategy.requirement_reports import numbered_requirements


class AnsweredRequirement(CamelModel):
    requirement: str = Field(
        description=(
            "The number of a requirement this criterion answers, such as R2, from "
            "'Requirements the researcher stated' in your instructions."
        )
    )
    param: str | None = Field(
        default=None,
        description=(
            "The parameter of the search that carries the requirement's value, "
            "from the sheet, or null when no one parameter carries it."
        ),
    )
    result_size: bool = Field(
        default=False,
        description=(
            "True when the requirement bounds how many records this criterion's "
            "step returns, so the step's count answers it; param is then null."
        ),
    )

    @model_validator(mode="after")
    def _a_result_size_names_no_parameter(self) -> AnsweredRequirement:
        if self.result_size and self.param is not None:
            msg = "result_size names no parameter: pass a null param with it"
            raise ValueError(msg)
        return self


def linked_requirements(
    state: AgentToolState,
    criterion_id: str,
    answers: Sequence[AnsweredRequirement] | None,
) -> list[RequirementLink]:
    if answers is None:
        return next(
            (
                list(c.answers)
                for c in state.operational_spec_draft.criteria
                if c.id == criterion_id
            ),
            [],
        )
    numbered = numbered_requirements(state.stated_requirements)
    unknown = [a.requirement for a in answers if a.requirement not in numbered]
    if unknown:
        msg = (
            f"answers names {unknown}, which the requirement list does not hold. "
            f"The list holds {', '.join(numbered) or 'none'}; name only those, or "
            f"pass an empty list when the criterion answers none of them."
        )
        raise ModelRetry(msg)
    return [
        RequirementLink(
            requirement=numbered[a.requirement].id,
            param=a.param,
            result_size=a.result_size,
        )
        for a in answers
    ]


def refuse_a_param_the_sheet_lacks(
    links: Sequence[RequirementLink], infos: Sequence[ParameterInfo]
) -> None:
    names = {info.name for info in infos}
    unknown = [link.param for link in links if link.param and link.param not in names]
    if unknown:
        msg = (
            f"answers names the parameters {unknown}, which the sheet does not "
            f"hold. The sheet holds {sorted(names) or 'none'}; name one of those "
            f"or pass a null param."
        )
        raise ModelRetry(msg)
