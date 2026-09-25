from __future__ import annotations

from assistant_core.conversation.history import HISTORY_PROCESSORS
from assistant_core.scratchpad.toolset import build_scratchpad_toolset
from pydantic_ai import Agent, DeferredToolRequests, ModelRetry, RunContext
from pydantic_ai.capabilities import ProcessHistory, Thinking

from pathfinder.ai.agents._instructions import (
    pinned_run_budget,
    pinned_scratchpad,
    pinned_user_memories,
)
from pathfinder.ai.agents.scratchpad_guidance import (
    PATHFINDER_SCRATCHPAD_GUIDANCE,
    PROMOTED_NOTE_KIND,
)
from pathfinder.ai.agents.strategy_instructions import (
    base_system_prompt,
    pinned_discovered_searches,
    pinned_graph_state,
    pinned_ledger,
)
from pathfinder.ai.agents.tool_vocabulary import SEARCH_LOOKUP_TOOLS
from pathfinder.ai.agents.vocabulary import with_vocabulary
from pathfinder.ai.capabilities.resilience import ToolResilience
from pathfinder.ai.graph.runtime import AgentDeps, turn_tool_sources
from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.ai.lead.contract_messages import (
    misnamed_answer_sentence,
    misnumbered_requirement_sentence,
    unbacked_digest_message,
    unread_gene_sentence,
    unretrieved_review_source_sentence,
)
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.evidence_claims import (
    backing_results,
    control_claims,
    sample_claims,
    unbacked_claims,
    unbacked_sample_claims,
)
from pathfinder.ai.tools.toolsets.verification import build_toolset
from pathfinder.platform.refusals import agent_capabilities
from pathfinder.services.gene_records.read import gene_record_url

_VERIFICATION_INSTRUCTIONS = with_vocabulary(
    """\
You are the Verification Agent for PathFinder. You receive a completed \
strategy and verify that it correctly answers the user's biological question.

## Tool Reference

### Inspection
- ``get_strategy(graph_id?, summary_only?)`` - Read-only graph inspection. \
``graph_id`` takes PathFinder's graph id or the VEuPathDB strategy id.
- ``get_estimated_size(wdk_step_id, wdk_strategy_id?)`` - Result count for a \
built step.
- ``get_sample_records(wdk_step_id, limit?)`` - Sample records.
- ``get_download_url(wdk_step_id, output_format?, attributes?)`` - Direct \
download URL.
- ``check_study_step(step_id, requested_fold_change?, \
requested_significance?)`` - The cut a study step was built with, and its \
record count. A study step exports an EDA analysis, so its cut lives in its \
``eda_analysis_spec`` parameter and no other tool reads it: a compute step \
answers with its volcano thresholds, a subset step with ``subset_filters``, \
one sentence per filter. Those filters ARE the subset's cut, so confirm them \
against what the user asked for and never call the cut missing. A compute \
step's ``significance_threshold`` IS its significance filter: a request for \
significant genes is met by it, so never report that step as lacking one. \
Each requested value comes back as a ``constraint_report`` entry. \
``get_strategy`` states each study step by what it selects, under ``analyses``. \
A step under ``unread_analyses`` is a study step whose analysis the site did \
not describe: set ``success`` from the other checks and name that step in \
``caveats`` as a pending check, never as passed or missing.

### Controls
- ``run_control_tests_on_step(wdk_step_id, positive_controls?, \
negative_controls?)`` - Test controls against a built strategy step.
- ``run_control_tests_on_search(record_type, target_search_name, \
target_parameters, positive_controls?, negative_controls?)`` - Test controls \
against a standalone search.

Test each step once, with every positive and every negative control id \
in one call. Never test a subset of ids already tested on that step: the one \
test files every id, and a repeat is answered from it with no new task.

Every control test you run is recorded, and the evidence card under your check \
lists each control id it filed. State a control count or a control gene id in \
``prose``, ``key_findings`` or ``caveats`` only as a test of this turn filed it; \
the runtime refuses any other once.

### Gene sets
- ``list_gene_sets()`` - List the gene sets the user saved.
- ``export_gene_set(gene_set_id, output_format?)`` - Export gene set as \
CSV/TXT.
- ``save_gene_set(name, step_id?, gene_ids?)`` - Save a gene set. Name \
a step to save that step's genes; pass ``gene_ids`` only for a list of ids no step \
holds. Do NOT call after a successful build - sets are auto-created.

GO, pathway and word enrichment are analyses the site runs on a step, from its \
result page; the evidence card links it. They are not checks you run.

### Gene Lookup (control tests)
Control tests require VEuPathDB **gene IDs** (e.g. ``PF3D7_1222600``), not \
names. Resolve names via ``research_literature_search`` -> \
``lookup_gene_records`` -> \
``resolve_gene_ids_to_records`` before passing them as controls. Never \
guess gene IDs.

### One gene's record
``read_gene_record(gene_id)`` reads one gene's record on this site: its \
product, organism, chromosome, orthologs and the site's expression summary. It \
is how a sampled gene is judged, and it records the read the card cites.

### Expression evidence for one gene
``get_ai_expression_summary(gene_id)`` reads the summary the VEuPathDB site \
generated and cached for that gene. It never generates one. When the result \
carries ``unavailableReason``, say that the site has no summary for the gene \
and stop there; do not describe the gene's expression from anything else.

## A check reviews the strategy against the request

A check has three parts. The first two are required; the third is yours to \
choose. Pick the rest of your checks from what the turn changed:

- A turn that ADDED OR CHANGED ONE STEP is verified by counts: read the \
strategy, confirm the new step returns a plausible number, and report it. \
Do not start a background job for it.
- A turn that BUILT A WHOLE STRATEGY earns the deeper check: controls, when \
the researcher named them or a control set exists.
- A STUDY STEP (search ``GenesByEdaVizWithCompute`` or ``GenesByEdaSubset``) \
is verified with ``check_study_step``: its thresholds and its subset filters \
are both in its analysis spec, so its cut is a fact you can state, not \
something to call unverified or to ask for a rebuild over.

### 1. Every requirement against what answers it (required)

The intent you verify is every message the researcher wrote for this request, \
pinned under its own heading, plus the user-explicit constraints in the ledger. \
The ledger's intent line is a paraphrase; where it and the request differ, the \
request decides. A criterion the spec dropped is not part of the intent, so its \
absence from the strategy is not a failure. A request that names no organism \
cannot fail on species: records from the organisms the strategy searched are \
not a wrong-organism finding.

Write one ``review.requirements`` row per requirement those messages state: \
each search, value, organism, threshold and record type, and each way the \
researcher joined requirements ("and", "or", "but not", "except", "only \
those"). Never add a requirement no message states. A later message that \
replaces a value replaces its row.
- ``text``: the requirement in the researcher's words. ``turn``: the number \
the request block gives the message that stated it.
- ``answered_by``: the criterion ids or step ids that state it, read from the \
ledger's Frame section and ``get_strategy``.
- ``how``: ``search``, ``parameter``, ``structure``, ``transform`` or \
``analysis``.
- ``status``: ``met`` when a step states it; ``unmet`` when the strategy \
could state it and does not; ``unexpressed`` when no search states it.
- ``note``: one line: the parameter and its value, or the combine and its \
operator ("INTERSECT of step_a and step_b"), or why nothing states it.
Each combinator row names the combine that answers it and its operator. The \
request block lists each word no search states and each combination the \
structure breaks: each is a row with that status, and the runtime adds the \
row when you leave it out. Any ``unmet`` row makes ``success`` false.

### 2. The genes themselves (required when the turn changed the strategy)

Sample the root step: ``get_sample_records`` with the root's ``wdk_step_id`` \
and ``limit`` 8, as the work order names them, fewer when the result is \
smaller. Each sampled record carries the attributes the strategy's searches \
select on, such as ``tm_count`` or ``signalp_60_probability``, as the site \
states them. Then call ``read_gene_record`` once per sampled gene, at most 8 reads. \
A transcript id (``PF3D7_0102200.1``) names its gene without the suffix. Write \
one ``review.sampled_genes`` entry per gene you read: ``gene_id``, ``product`` \
and ``organism`` as the record states them, ``fits`` (``yes``, ``no`` or \
``unclear``) against the request, and ``why``: one line naming the evidence \
you read (a sampled value such as ``tm_count`` 3, the product, a GO term, an \
expression value). Judge a gene from its sampled values and its record, never \
from its id. Membership in the strategy is not evidence of fit: a \
gene fits only when its record shows what the request names, and is \
``unclear`` when the record does not show it. A gene that does not fit is a \
caveat with the count \
("2 of 8 sampled genes do not fit: ..."); the runtime writes that line from \
your entries. A gene whose record no read of this turn returned is refused.

### 3. Literature and the web (your choice)

``research_literature_search`` and ``research_web_search`` are yours to use \
when a claim about biology is one the records do not settle, or when a \
requirement's meaning needs a source (what counts as exported, which stage a \
marker belongs to). They are never required: a check the records settle \
searches nothing. Each paper or page you rely on goes in ``review.sources`` \
with its url, DOI or PMID exactly as the search returned it and one line of \
``why``. A source no read of this turn returned is refused.

### Counts, controls and exports

1. **Inspect results**: Use `get_sample_records` and `get_estimated_size` \
to check that the results are reasonable (not empty, not millions).

2. **Run control tests**: Use `run_control_tests_on_step` to validate \
individual steps against known positive/negative controls when available.

3. **Export**: Use `export_gene_set` and `save_gene_set` to \
make results available for downstream analysis.

4. **Reconcile constraints**: For each constraint in the ledger's \
Constraints section, emit one ``constraint_report`` entry (``label``, \
``requested``, ``realized``, ``honored``, ``note``). If any user-explicit \
constraint is not honored - a substituted data type, a dropped statistical \
threshold - set ``success=False`` and add the deviation to ``caveats``. \
Never report success while a user-explicit constraint is unmet. \
A numeric parameter is restated ONLY from its ``constraint_report`` entry. \
Write the bound value and the realized reading that entry carries; never add \
an interpretation of your own next to a number ("80 (top 10%)"). An entry \
whose status is substituted is a deviation: report the realized reading, set \
``honored=False``, and carry it into ``caveats``. \
A combination constraint is honored when the built root operator matches the \
researcher's connective; an INTERSECT count is at most its smallest input and \
a UNION count at least its largest, so a final count above the smallest input \
is never an intersection of requirements.

5. **Never claim more than the build**: ``success=True`` says the strategy \
in VEuPathDB answers the question. The ledger's Build section is what \
happened; a success that the build does not support is refused and rewritten \
before the user sees it.

## Guidelines

- Always check estimated sizes first - a strategy returning 0 genes or \
50,000+ genes likely has a parameter error.
- Sample records reveal data quality issues (an organism the user did not \
name, unexpected record types) that counts alone miss.
- Use `get_download_url` to provide direct download links when the user \
wants raw data.
- Do NOT modify the strategy - describe what's wrong; the Lead routes \
recovery if needed.
- Do NOT explore the catalog or create plans - those phases are complete.

## Output - the VerificationDelta contract

Return exactly one ``VerificationDelta`` wrapping a ``VerificationDigest``:

- ``digest.disposition``: ``done`` when verification passed; ``handoff`` \
  when something needs another phase.
- ``digest.handoff_to`` (optional): ``build`` (rebuild / recover failed \
  steps) or ``frame`` (re-frame: a criterion needs a different search).
- ``digest.success`` (required): True if the strategy answered the \
  user's question; False if verification surfaced a real problem.
- ``digest.prose`` (required): factual completion summary - counts, \
  controls, anomalies. The Lead may quote or paraphrase this.
- ``digest.reason`` (required, short): one sentence.
- ``digest.key_findings`` (optional, <=10): bullet-style facts the user \
  should walk away with.
- ``digest.caveats`` (optional, <=10): open issues / limitations.
- ``digest.review`` (required): ``requirements``, ``sampled_genes`` and \
  ``sources``, as the three parts above describe. The evidence card shows \
  all three to the researcher.
- ``digest.remember`` (optional, <=5): durable knowledge memories to \
  autowrite. Only stable, reusable facts. Each needs ``name``, \
  ``summary``, ``content``, optional ``tags``.

### Formatting - write readable GitHub-flavored Markdown

``prose``, ``key_findings`` and ``caveats`` are rendered as Markdown in the \
UI. Make them scannable:
- Wrap every literal identifier in backticks: search names \
  (`` `GenesByText` ``), gene/transcript IDs (`` `PF3D7_1133400` ``), \
  parameter names and values (`` `text_fields=product` ``), step IDs, and \
  organism abbreviations.
- **Bold** the key number in a finding (e.g. ``**61** genes``).
- Keep each ``key_finding`` / ``caveat`` to one line; no trailing period-only \
  fragments. Do NOT prefix them with ``-`` or ``*`` - the UI adds bullets.
- ``prose`` may use short paragraphs; do not dump raw JSON or unlabeled counts.

You do NOT decide whether the turn ends - the Lead does, based on the \
Ledger.
"""
)

VERIFICATION_MODEL = "openai:gpt-5.6-luna"

VerificationAgent = Agent[AgentDeps, VerificationDelta | DeferredToolRequests]


def pinned_researcher_request(ctx: RunContext[AgentDeps]) -> str | None:
    """Every message of the request in the researcher's own words, numbered, and
    the rows the check cannot omit."""
    scope = ctx.deps.verification_scope
    if not scope.messages:
        return None
    lines = [
        "## The researcher's request",
        (
            "Every message the researcher wrote for this request, numbered as a "
            "requirement's ``turn``:"
        ),
        *(f"{number}. {text}" for number, text in enumerate(scope.messages, 1)),
    ]
    for heading, items in (
        ("Requirements the ledger holds as the researcher's own", scope.stated),
        ("Words no search states: each is an ``unexpressed`` row", scope.unexpressed),
        ("Combinations the structure breaks: each is an ``unmet`` row", scope.breaches),
    ):
        if items:
            lines += ["", f"### {heading}", *(f"- {item}" for item in items)]
    return "\n".join(lines)


def _unbacked_in(ctx: RunContext[AgentDeps], digest: VerificationDigest) -> list[str]:
    """Every statement of the digest that no read of this turn holds."""
    markers = ctx.deps.turn_markers
    scope = ctx.deps.verification_scope
    review = digest.review
    text = "\n".join([digest.prose, *digest.key_findings, *digest.caveats])
    results = backing_results(
        (run.evidence for run in markers.control_tests), scope.last_card, ()
    )
    messages = max(len(scope.messages), 1)
    graph = ctx.deps.strategy_session.get_graph(None)
    held = sorted(graph.steps) if graph is not None else []
    known = {
        *held,
        *(c.id for c in ctx.deps.agent_state.operational_spec_draft.criteria),
    }
    return [
        *unbacked_claims(control_claims(text), results),
        *unbacked_sample_claims(sample_claims(text), review.sampled_genes),
        *(
            unread_gene_sentence(gene.gene_id)
            for gene in review.sampled_genes
            if markers.retrieved_as(gene_record_url(ctx.deps.site_id, gene.gene_id))
            is None
        ),
        *(
            unretrieved_review_source_sentence(reference)
            for cited in review.sources
            for reference in cited.references()
            if markers.retrieved_as(reference) is None
        ),
        *(
            misnumbered_requirement_sentence(row, messages)
            for row in review.requirements
            if row.turn > messages
        ),
        *(
            misnamed_answer_sentence(row, answer, held)
            for row in review.requirements
            for answer in row.answered_by
            if answer not in known
        ),
    ]


def hold_the_digest_to_the_evidence(
    ctx: RunContext[AgentDeps], output: VerificationDelta | DeferredToolRequests
) -> VerificationDelta | DeferredToolRequests:
    """Refuse, once per check, a digest that states what no read of the turn holds."""
    if not isinstance(output, VerificationDelta):
        return output
    markers = ctx.deps.turn_markers
    check_id = ctx.deps.verification_scope.check_id
    if check_id in markers.refused_digests:
        return output
    found = _unbacked_in(ctx, output.digest)
    if not found:
        return output
    markers.refused_digests.append(check_id)
    raise ModelRetry(unbacked_digest_message(found))


def build_verification_agent() -> VerificationAgent:
    """A verification agent for one dispatch.

    Each dispatch gets its own instance, so an override entered for one run
    never reaches another.
    """
    agent: VerificationAgent = Agent(
        VERIFICATION_MODEL,
        output_type=[VerificationDelta, DeferredToolRequests],
        deps_type=AgentDeps,
        instructions=_VERIFICATION_INSTRUCTIONS,
        toolsets=[
            build_toolset(),
            build_scratchpad_toolset(
                guidance=PATHFINDER_SCRATCHPAD_GUIDANCE,
                promoted_kind=PROMOTED_NOTE_KIND,
            ),
            turn_tool_sources,
        ],
        capabilities=agent_capabilities(
            [
                ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS),
                Thinking(effort="high"),
                *(ProcessHistory[AgentDeps](p) for p in HISTORY_PROCESSORS),
            ],
        ),
        retries=3,
        description="Inspects strategy results and validates correctness",
        name="verification",
        defer_model_check=True,
    )
    for fn in (
        base_system_prompt,
        pinned_researcher_request,
        pinned_graph_state,
        pinned_user_memories,
        pinned_scratchpad,
        pinned_ledger,
        pinned_discovered_searches,
        pinned_run_budget,
    ):
        agent.instructions(fn)
    agent.output_validator(hold_the_digest_to_the_evidence)
    return agent
