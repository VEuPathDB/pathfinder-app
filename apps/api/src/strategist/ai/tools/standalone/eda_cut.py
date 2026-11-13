from __future__ import annotations

from collections.abc import Mapping

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb.eda import EdaStudyDetail

from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.tools.standalone._eda_sheet import sheet_entries
from strategist.ai.tools.standalone.eda_analysis import bound_analysis
from strategist.domain.eda_cut import TailEdge
from strategist.domain.strategy.question_options import TailRule
from strategist.domain.strategy.questions import OpenQuestion
from strategist.services.eda.catalog import get_study_detail_for_dataset
from strategist.services.eda.cut_offer import (
    OfferedCut,
    counted_noun,
    study_cut_question,
    study_tail_edges,
)

_CLASS_SIZE = 8


def picked_rule_sentences(
    edges: Mapping[str, TailEdge], variable_name: str, noun: str
) -> str:
    return " ".join(
        f'The researcher picked "{label}" on a card, the {edge.rule.end}est '
        f"{edge.rule.percent}% of a study. On this study's {variable_name} "
        f"that is {edge.cut(noun)}, so send {edge.wire_end}={edge.bound:g}."
        for label, edge in edges.items()
    )


def ask_sentence(question: OpenQuestion) -> str:
    if not question.options:
        return (
            "This study counts no cut to offer. Ask the researcher for the cut "
            "in their own words with consult_user, in a question with no options."
        )
    return (
        f'Call consult_user: the card asks "{question.question}" with the cuts '
        f"this study counts, as recorded, so write no question or option of your "
        f"own for this cut."
    )


async def cut_card(
    site_id: str,
    dataset_id: str,
    study: EdaStudyDetail,
    *,
    entity_id: str,
    variable_id: str,
    variable_name: str,
    numeric: bool,
) -> OpenQuestion:
    classes = [
        (e.variable_id, e.display_name)
        for e in sheet_entries(study)
        if e.entity_id == entity_id
        and e.filter_type == "stringSet"
        and 0 < e.vocabulary_total <= _CLASS_SIZE
    ]
    return await study_cut_question(
        site_id,
        dataset_id=dataset_id,
        study=study,
        cut=OfferedCut(
            entity_id=entity_id,
            variable_id=variable_id,
            variable_name=variable_name,
            numeric=numeric,
            classes=classes,
        ),
    )


async def ask_eda_cut(
    ctx: RunContext[LeadDeps], *, variable_id: str
) -> ToolReturn[str]:
    """Ask the researcher where to cut one variable of the open analysis.

    Call this when the researcher has not said where to cut a variable, before
    any filter on it. Code counts the study's own cuts (its classes, and the
    lowest and highest 5% and 10% of a number) into a card, and consult_user
    asks that card as recorded. When the researcher already picked a tail on
    another study, this returns the bound that tail gives on this study.

    Args:
        ctx: Agent run context.
        variable_id: The variable the cut reads, from the filter sheet.
    """
    site_id = ctx.deps.runtime.site_id
    bound = await bound_analysis(ctx)
    if bound is None:
        msg = "This conversation has no study open. Call open_eda_analysis first."
        raise ModelRetry(msg)
    _entry, study = await get_study_detail_for_dataset(site_id, bound.dataset_id)
    entries = sheet_entries(study)
    entry = next((e for e in entries if e.variable_id == variable_id), None)
    if entry is None:
        numbers = ", ".join(
            f"{e.display_name} ({e.variable_id})"
            for e in entries
            if e.filter_type == "numberRange"
        )
        msg = (
            f"{variable_id} is no variable of this study. Its numeric variables "
            f"are {numbers or 'none'}."
        )
        raise ModelRetry(msg)
    thread = ctx.deps.state.domain
    numeric = entry.filter_type == "numberRange"
    rules: Mapping[str, TailRule] = (
        thread.tail_rules_on(entry.display_name) if numeric else {}
    )
    edges = await study_tail_edges(
        site_id,
        dataset_id=bound.dataset_id,
        study=study,
        entity_id=entry.entity_id,
        variable_id=variable_id,
        rules=rules,
    )
    if edges:
        noun = counted_noun(study, entry.entity_id)
        said = (
            f"{picked_rule_sentences(edges, entry.display_name, noun)} Set that "
            f"filter with set_eda_filters, then call create_eda_step."
        )
        return with_summary(
            said, f"Read the picked tail on {entry.display_name}", ctx=ctx
        )
    question = await cut_card(
        site_id,
        bound.dataset_id,
        study,
        entity_id=entry.entity_id,
        variable_id=variable_id,
        variable_name=entry.display_name,
        numeric=numeric,
    )
    if question.options:
        thread.record_questions([question])
    return with_summary(
        ask_sentence(question),
        f"Counted {len(question.options)} cuts of {entry.display_name}",
        ctx=ctx,
    )
