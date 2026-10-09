"""Every arc a test message can name, by the name its token carries."""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call, terminal_call
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock import (
    edit_arcs,
    frame_arcs,
    frame_edits,
    kept_arcs,
    phrase_label_arcs,
    prose_arcs,
    strategy_specs,
    unset_value_arcs,
)
from pathfinder.ai.models.mock.arc import Arc, Script, Sequence, history_free
from pathfinder.ai.models.mock.calls import classify, lead_final, narrated
from pathfinder.ai.models.mock.consult_arc import consult, open_value_frame, withdraw
from pathfinder.ai.models.mock.control_flow_arcs import (
    comparison_after_a_refused_union,
    count_comparison,
    read_again,
    reclassified,
    union_frame,
)
from pathfinder.ai.models.mock.count_answer_arcs import derived_count
from pathfinder.ai.models.mock.eda_arc import (
    eda_compare,
    eda_compare_no_step,
    eda_other_site,
)
from pathfinder.ai.models.mock.facts_arcs import list_ids
from pathfinder.ai.models.mock.frame_arcs import spec_frame
from pathfinder.ai.models.mock.lead_flow import (
    build_journey,
    build_when_framed,
    edit_journey,
    extend_or_build,
    framed_only,
    lead,
    thread_is_framed,
)
from pathfinder.ai.models.mock.lifecycle_arcs import (
    narrowed_organism,
    withdrawn_requirement,
)
from pathfinder.ai.models.mock.lookup_arcs import odorant_binding_frame
from pathfinder.ai.models.mock.note_arc import noted
from pathfinder.ai.models.mock.reads import frame_summary
from pathfinder.ai.models.mock.requirement_arcs import comparison_sides, widen_card
from pathfinder.ai.models.mock.separation_arc import separation
from pathfinder.ai.models.mock.user_dataset_arc import user_dataset_deseq
from pathfinder.ai.models.mock.verify_arc import verification

_LOOP_PROSE = (
    "I kept re-reading the same catalog listing and made no progress, so I "
    "stopped there."
)
_SYNTENY_PROSE = (
    "**The site holds no syntenic orthologs here.** The transform returned no "
    "genes: synteny is not recorded between these organisms."
)
_CROSS_PROSE = (
    "I built nothing: gene ids of two species never match, so that INTERSECT "
    "always returns no genes. I can carry the first set to its orthologs in the "
    "second organism instead."
)

default_frame = spec_frame(strategy_specs.single_spec)
default_verification = verification(site_controls=False)


def _recovery() -> ToolCallPart:
    return terminal_call({"actionsTaken": ["[mock] recovery"], "followUpNeeded": False})


def _arc(
    lead_script: Script,
    *,
    frame: Script = default_frame,
    verify: Script = default_verification,
) -> Arc:
    return Arc(
        lead=lead_script,
        frame=frame,
        verification=verify,
        execution=history_free(_recovery),
    )


def _built(spec_frame_script: Script, journey: Sequence = build_journey) -> Arc:
    return _arc(lead(journey), frame=spec_frame_script)


def _synteny(messages: list[ModelMessage]) -> list[ToolCallPart]:
    return extend_or_build(messages, failure=_SYNTENY_PROSE)


def _portal(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Frame or edit, then state the route the pass answered, building nothing."""
    if not thread_is_framed(messages):
        return framed_only(messages, _summary_prose)
    return [
        classify("edit_strategy"),
        scripted_call("edit_strategy", {"reason": "mock edit"}),
        lead_final(_summary_prose(messages), "await_user"),
    ]


def _assent(messages: list[ModelMessage]) -> list[ToolCallPart]:
    return build_journey(messages, classification="extend_strategy")


def _summary_prose(messages: list[ModelMessage]) -> str:
    """What the pass found in words, with nothing built: the facts part beside
    the reply shows the plan's values and counts."""
    return narrated(f"{frame_summary(messages)} I built nothing.")


def _loop(messages: list[ModelMessage]) -> list[ToolCallPart]:
    return framed_only(messages, history_free(lambda: _LOOP_PROSE))


def _cross(messages: list[ModelMessage]) -> list[ToolCallPart]:
    return framed_only(messages, history_free(lambda: _CROSS_PROSE))


def _built_when_framed(messages: list[ModelMessage]) -> list[ToolCallPart]:
    return build_when_framed(messages, _summary_prose)


def _summarized(messages: list[ModelMessage]) -> list[ToolCallPart]:
    return framed_only(messages, _summary_prose)


ARCS: dict[str, Arc] = {
    "single": _built(default_frame),
    "intersect": _built(noted(spec_frame(strategy_specs.intersect_spec))),
    "union": _built(spec_frame(strategy_specs.union_spec)),
    "minus": _built(spec_frame(strategy_specs.minus_spec)),
    "orthologs": _built(frame_edits.orthologs_frame, extend_or_build),
    "syntenic-orthologs": _built(frame_edits.syntenic_frame, _synteny),
    "round-trip": _built(frame_edits.round_trip_frame, extend_or_build),
    "go": _built(spec_frame(strategy_specs.go_spec)),
    "combined": _built(spec_frame(strategy_specs.combined_spec)),
    "count-question": _built(spec_frame(strategy_specs.count_spec)),
    "second-build": _built(default_frame),
    "assent": _built(default_frame, _assent),
    "controls-test": _arc(
        lead(kept_arcs.controls_test), verify=verification(site_controls=True)
    ),
    "zero-then-relax": _built(frame_edits.relax_frame, extend_or_build),
    "edit-param": _built(frame_edits.edit_param_frame, edit_journey),
    "add-step": _built(frame_edits.add_step_frame, edit_journey),
    "replace-subtree": _built(frame_edits.replace_frame, edit_journey),
    "delete-step-card": _arc(lead(edit_arcs.delete_card)),
    "clear": _arc(lead(edit_arcs.clear)),
    "proposal": _arc(lead(edit_arcs.proposal), frame=frame_edits.add_step_frame),
    "sweep": _arc(lead(edit_arcs.sweep)),
    "consult": _arc(consult, frame=open_value_frame),
    "withdraw": _arc(withdraw),
    "no-search-states-it": _arc(lead(_summarized), frame=frame_arcs.no_search_frame),
    "cross-organism": _arc(lead(_cross), frame=frame_arcs.cross_organism_frame),
    "portal-only": _arc(lead(_portal), frame=frame_arcs.portal_frame),
    "other-site-experiment": _arc(
        lead(_built_when_framed), frame=frame_arcs.other_site_frame
    ),
    "frame-loop": _arc(lead(_loop), frame=history_free(frame_arcs.loop_frame)),
    "separation": _arc(lead(separation)),
    "variants": _arc(lead(kept_arcs.variants)),
    "save-gene-set": _arc(lead(history_free(kept_arcs.save_gene_set))),
    "export": _arc(lead(kept_arcs.export)),
    "remember": _arc(lead(history_free(kept_arcs.remember))),
    "recall-preference": _arc(lead(kept_arcs.recall_preference)),
    "recall": _arc(lead(history_free(kept_arcs.recall))),
    "recap": _arc(lead(kept_arcs.recap)),
    "attachment": _arc(lead(kept_arcs.attachment)),
    "gene-question": _arc(lead(kept_arcs.gene_question)),
    "eda-compare": _arc(eda_compare),
    "eda-compare-no-step": _arc(eda_compare_no_step),
    "eda-other-site": _arc(eda_other_site),
    "user-dataset-deseq": _arc(user_dataset_deseq),
    "off-topic": _arc(lead(history_free(prose_arcs.off_topic))),
    "kinase-question": _arc(lead(history_free(prose_arcs.kinase_question))),
    "impact": _arc(lead(history_free(prose_arcs.impact))),
    "context": _arc(lead(history_free(prose_arcs.context))),
    "rename": _arc(lead(edit_arcs.rename)),
    "echo": _arc(lead(prose_arcs.echo)),
    "organism-universe": _built(spec_frame(strategy_specs.organism_universe_spec)),
    "radio-off-domain": _built(spec_frame(unset_value_arcs.radio_off_domain_spec)),
    "text-beside-organism": _built(
        spec_frame(unset_value_arcs.text_beside_organism_spec)
    ),
    "reclassified": _arc(reclassified),
    "read-again": _arc(read_again),
    "count-comparison": _arc(lead(count_comparison)),
    "union-refused": _arc(lead(comparison_after_a_refused_union), frame=union_frame),
    "comparison-sides": _arc(lead(comparison_sides)),
    "widen-card": _arc(lead(widen_card)),
    "list-ids": _arc(lead(list_ids)),
    "odorant-lookup": _built(odorant_binding_frame),
    "derived-count": _arc(lead(derived_count)),
    "muris-phrase": _built(spec_frame(phrase_label_arcs.muris_phrase_spec)),
    "narrowed-organism": _arc(lead(narrowed_organism)),
    "withdrawn-requirement": _arc(lead(withdrawn_requirement)),
}


class UnknownArcError(LookupError):
    """A message names an arc the registry does not hold."""


def arc_named(name: str) -> Arc:
    if name not in ARCS:
        msg = f"No mock arc is named {name!r}. Known arcs: {sorted(ARCS)}"
        raise UnknownArcError(msg)
    return ARCS[name]
