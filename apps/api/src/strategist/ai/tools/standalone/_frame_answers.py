from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field, model_validator
from veupathdb.model import CamelModel
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.agents.state import AgentToolState
from strategist.domain.refusal import Problem, Problems, RefusalKey
from strategist.domain.strategy.operational_spec import RequirementLink
from strategist.domain.strategy.requirement_reports import numbered_requirements


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
) -> tuple[list[RequirementLink], Problems]:
    """The requirements the criterion answers, and the problem a number the
    requirement list does not hold makes."""
    if answers is None:
        held = next(
            (
                list(c.answers)
                for c in state.operational_spec_draft.criteria
                if c.id == criterion_id
            ),
            [],
        )
        return held, Problems()
    numbered = numbered_requirements(state.stated_requirements)
    unknown = [a.requirement for a in answers if a.requirement not in numbered]
    links = [
        RequirementLink(
            requirement=numbered[a.requirement].id,
            param=a.param,
            result_size=a.result_size,
        )
        for a in answers
        if a.requirement in numbered
    ]
    if not unknown:
        return links, Problems()
    return links, Problems.one(
        RefusalKey(check="requirements"),
        f"answers names {unknown}, which the requirement list does not hold. "
        f"The list holds {', '.join(numbered) or 'none'}; name only those, or "
        f"pass an empty list when the criterion answers none of them.",
    )


def answers_the_sheet_lacks(
    links: Sequence[RequirementLink], infos: Sequence[ParameterInfo]
) -> Problems:
    names = sorted(info.name for info in infos)
    return Problems(
        found=tuple(
            Problem(
                key=RefusalKey(check="answers", parameter=link.param),
                sentence=(
                    f"answers names the parameters {[link.param]}, which the sheet "
                    f"does not hold. The sheet holds {names or 'none'}; name one of "
                    f"those or pass a null param."
                ),
            )
            for link in links
            if link.param and link.param not in names
        )
    )
