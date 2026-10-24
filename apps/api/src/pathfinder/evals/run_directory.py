"""The scorer's observation, read from a chat-debugger run directory captured with
its WDK exchanges, so a run is graded after its database is gone."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from veupathdb.devtools import WDKExchange
from veupathdb.domain.parameters import PhyleticTree
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, fold, walk
from veupathdb.wdk import WDKStrategyDetails
from veupathdb_mcp.wdk import WireStep, build_snapshot_from_wdk

from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.devtools.gates import Gate, consult_labels, gate_end
from pathfinder.devtools.models import PhaseSnapshot
from pathfinder.evals.case import EvalCase, ExpectedOutcome
from pathfinder.evals.count_unit import counts_in_genes
from pathfinder.evals.distance import COMBINE_LABEL, ComparisonNode
from pathfinder.evals.phrases import shown
from pathfinder.evals.scoring import (
    ObservedOutcome,
    final_count_below_every_input,
    root_count,
    root_operator,
    step_titles,
    structure_signature,
)
from pathfinder.evals.summary import CaseResult, judged

_TURN = re.compile(r"^turn-(\d+)$")
_ANSWER = re.compile(r"^answer-(\d+)$")
_STRATEGY_READ = re.compile(r"^(\d+)-GET-\d+\.json$")
_STRATEGY_PATH = re.compile(r"/strategies/\d+$")
_REPLY = "\n## Reply\n\n"
_FACTS = "\n## Facts\n\n"
_ASSUMED = "\n\n## Assumed\n"


class UnobservedFieldError(ValueError):
    pass


def _numbered(directory: Path, pattern: re.Pattern[str]) -> list[Path]:
    found = [
        (int(match[1]), path)
        for path in directory.iterdir()
        if path.is_dir() and (match := pattern.match(path.name))
    ]
    return [path for _, path in sorted(found)]


def _turns(case_dir: Path) -> list[list[Path]]:
    return [[turn, *_numbered(turn, _ANSWER)] for turn in _numbered(case_dir, _TURN)]


def _strategy_reads(part: Path) -> list[WDKStrategyDetails]:
    wdk = part / "wdk"
    numbered = (
        (int(match[1]), path)
        for path in (wdk.iterdir() if wdk.is_dir() else [])
        if (match := _STRATEGY_READ.match(path.name))
    )
    exchanges = [
        WDKExchange.model_validate_json(path.read_text())
        for _, path in sorted(numbered)
    ]
    return [
        WDKStrategyDetails.model_validate(exchange.response_json)
        for exchange in exchanges
        if _STRATEGY_PATH.search(urlparse(exchange.url).path)
    ]


def _shape(read: WDKStrategyDetails) -> tuple[object, ...]:
    steps = {
        step_id: (step.search_name, step.search_config.parameters)
        for step_id, step in read.steps.items()
    }
    return (read.step_tree, steps)


def _section(transcript: str, heading: str) -> str:
    if heading not in transcript:
        return ""
    body = transcript.split(heading, 1)[1].rsplit(_ASSUMED, 1)[0]
    return body.split("\n\n## Reply\n", 1)[0].strip()


def _verified(turn: Path) -> bool | None:
    snapshot = turn / "state" / "verification.json"
    if not snapshot.is_file():
        return None
    ledger = PhaseSnapshot.model_validate_json(snapshot.read_text()).ledger
    if ledger is None:
        return None
    digest = InvestigationLedger.model_validate(ledger).verification.digest
    return None if digest is None else digest.passed


def _tree(ast: StrategyAst, wire: dict[str, WireStep]) -> ComparisonNode:
    def node(step: StrategyStepNode, inputs: list[ComparisonNode]) -> ComparisonNode:
        combine = step.infer_kind() == "combine"
        return ComparisonNode(
            search_name=COMBINE_LABEL if combine else step.search_name,
            operator=step.operator.value if step.operator is not None else None,
            parameters={} if combine else wire[step.id].parameters,
            children=tuple(inputs),
        )

    return fold(ast.root, node)


def _verdict(parts: list[Path], reads: list[WDKStrategyDetails]) -> bool | None:
    for part in reversed(parts):
        verdict = _verified(part)
        if verdict is None:
            continue
        judged = _strategy_reads(part)
        if not judged or _shape(judged[-1]) != _shape(reads[-1]):
            return None
        return verdict
    return None


def observed_from_run_directory(case_dir: Path) -> ObservedOutcome:
    turns = _turns(case_dir)
    parts = [part for turn in turns for part in turn]
    transcripts = [
        [(part / "transcript.md").read_text() for part in turn] for turn in turns
    ]
    replies = [_section(texts[-1], _REPLY) for texts in transcripts]
    facts = [
        next((f for t in reversed(texts) if (f := _section(t, _FACTS))), "")
        for texts in transcripts
    ]
    reads = [read for part in parts for read in _strategy_reads(part)]
    gate = Gate.model_validate_json((parts[-1] / "gate.json").read_text())
    reply, last_facts = replies[-1], facts[-1]
    observed = ObservedOutcome(
        built_strategy=bool(reads),
        reply_text=reply,
        facts_text=last_facts,
        turn_replies=replies,
        turn_facts=facts,
        ends_on=gate_end(gate),
        consult_options=consult_labels(gate),
    )
    if not reads:
        return observed
    ast, wire = build_snapshot_from_wdk(reads[-1])
    return observed.model_copy(
        update={
            "verified": _verdict(parts, reads),
            "structure": structure_signature(ast),
            "record_type": ast.record_type,
            "step_count": len(list(walk(ast.root))),
            "tree": _tree(ast, wire),
            "step_titles": step_titles(ast),
            "counts_in_genes": counts_in_genes(shown(last_facts, reply), ast),
            "root_operator": root_operator(ast),
            "final_count_below_every_input": final_count_below_every_input(ast),
            "root_count": root_count(ast),
        }
    )


def _unobserved(expected: ExpectedOutcome) -> list[str]:
    stated = {
        "replyGivesItsReasons": expected.reply_gives_its_reasons,
        "metRequirements": expected.met_requirements is not None,
        "unmetRequirements": expected.unmet_requirements is not None,
        "unexpressedRequirements": expected.unexpressed_requirements is not None,
        "sameRecordsAs": bool(expected.same_records_as),
        "stepIdsUnchanged": expected.step_ids_unchanged is not None,
        "assumedStated": expected.assumed_stated is not None,
    }
    return [field for field, held in stated.items() if held]


def score_run_directory(
    case: EvalCase, case_dir: Path, taxonomy: PhyleticTree | None, build: str
) -> CaseResult:
    unobserved = _unobserved(case.expected)
    if unobserved:
        msg = f"a run directory does not hold {', '.join(unobserved)}"
        raise UnobservedFieldError(msg)
    return judged(case, observed_from_run_directory(case_dir), build, taxonomy)


__all__ = [
    "UnobservedFieldError",
    "observed_from_run_directory",
    "score_run_directory",
]
