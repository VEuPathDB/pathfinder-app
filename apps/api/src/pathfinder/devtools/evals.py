"""The curation desk and the eval run command.

Usage::

    python -m pathfinder.devtools.evals staged
    python -m pathfinder.devtools.evals show <staging-id>
    python -m pathfinder.devtools.evals promote <staging-id> --name <case-name> \\
        --rationale "what this pins" [--turn ...] [--note ...]
    python -m pathfinder.devtools.evals corpus
    python -m pathfinder.devtools.evals run [--only NAME ...] [--out FILE] [--real]

``promote`` writes the corpus file and ends the association: the staged row
keeps its content hash and loses its user, its thread and its extract.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from assistant_core.platform.db import async_session_factory

from pathfinder.devtools import chat
from pathfinder.devtools.chat import route_framework_logs_to_stderr
from pathfinder.devtools.eval_runner import run_corpus
from pathfinder.evals.case import ExpectedOutcome
from pathfinder.evals.store import CORPUS_DIR, load_corpus
from pathfinder.persistence.repositories.eval_staging import EvalStagingRepository
from pathfinder.services.eval_data.curation import (
    PromotionEdits,
    default_expectation,
    promote_staged_case,
    staged_extract,
)
from pathfinder.services.eval_data.extraction import extract_eval_candidates

# Beside the chat debugger's artifacts, so an eval run is inspectable with the
# same commands.
RUN_ROOT = chat.RUN_ROOT / "evals"


def _staging() -> EvalStagingRepository:
    return EvalStagingRepository(session_factory=async_session_factory)


def _origin(rated_message_id: UUID | None, turn_count: int) -> str:
    """How the row was staged: the thread's extraction, or a disliked turn."""
    if rated_message_id is None:
        return "extracted"
    return f"disliked turn {turn_count}"


async def _list_staged() -> int:
    rows = await _staging().list_staged()
    if not rows:
        print("no staged candidates")
        return 0
    for row in rows:
        extract = staged_extract(row)
        first = extract.turns[0].request if extract.turns else ""
        built = "built" if extract.strategy is not None else "no build"
        origin = _origin(row.rated_message_id, len(extract.turns))
        print(
            f"{row.id}  {row.site_id:12} {row.assistant_id:12} {built:9} "
            f"{origin:18} {first[:60]}"
        )
    print(f"{len(rows)} staged candidate(s)")
    return 0


async def _show(staging_id: UUID) -> int:
    row = await _staging().get(staging_id)
    if row is None:
        print(f"no staged case {staging_id}", file=sys.stderr)
        return 2
    extract = staged_extract(row)
    print(f"staging id : {row.id}")
    print(f"site       : {row.site_id}")
    print(f"assistant  : {row.assistant_id}")
    print(f"staged at  : {row.staged_at.isoformat()}")
    print(f"origin     : {_origin(row.rated_message_id, len(extract.turns))}")
    for index, turn in enumerate(extract.turns, 1):
        print(f"\n--- turn {index} request ---\n{turn.request}")
        if turn.reply:
            print(f"--- turn {index} reply ---\n{turn.reply}")
    if extract.strategy is not None:
        print(f"\nstructure  : {extract.strategy.structure}")
        print(f"steps      : {extract.strategy.step_count}")
    if extract.verification is not None:
        print(f"verified   : {extract.verification.passed}")
        print(f"reason     : {extract.verification.reason}")
        evidence = extract.verification.evidence
        if evidence is not None:
            print(f"evidence   : {evidence.model_dump_json(indent=2, by_alias=True)}")
    print("\nsuggested expectation:")
    print(default_expectation(row).model_dump_json(indent=2, by_alias=True))
    return 0


async def _promote(args: argparse.Namespace) -> int:
    path = await promote_staged_case(
        staging=_staging(),
        staging_id=UUID(args.staging_id),
        edits=PromotionEdits(
            name=args.name,
            rationale=args.rationale,
            turns=args.turn or None,
            expected=(
                None
                if args.expect is None
                else ExpectedOutcome.model_validate_json(args.expect)
            ),
            curator_note=args.note,
        ),
    )
    print(f"promoted -> {path}")
    return 0


async def _extract_now() -> int:
    report = await extract_eval_candidates()
    print(
        f"considered={report.considered} staged={report.staged} "
        f"skipped={report.skipped}",
    )
    return 0


_BUILD_LABELS: dict[bool | None, str] = {
    True: "builds",
    False: "no build",
    None: "either",
}


def _list_corpus() -> int:
    cases = load_corpus()
    for case in cases:
        build = _BUILD_LABELS[case.expected.builds_strategy]
        print(f"{case.name:52} {case.site_id:10} {build:9} {case.provenance.origin}")
    print(f"{len(cases)} case(s) in {CORPUS_DIR}")
    return 0


def _run(args: argparse.Namespace) -> int:
    summary = asyncio.run(
        run_corpus(
            run_root=RUN_ROOT, only=args.only, mock=not args.real, effort=args.effort
        ),
    )
    if args.out:
        payload = summary.model_dump(by_alias=True, mode="json")
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
    for case in summary.cases:
        mark = "PASS" if case.passed else "FAIL"
        print(f"{mark}  {case.name}  {case.duration_seconds}s")
        if case.distance is not None:
            print(
                f"      distance: topology {case.distance.topology}, "
                f"searches {case.distance.search_selection}, "
                f"labelled {case.distance.labelled}, "
                f"parameter fidelity {case.distance.parameter_fidelity}",
            )
        if case.error:
            print(f"      error: {case.error}")
        for difference in case.differences:
            print(
                f"      {difference.field}: expected {difference.expected!r}, "
                f"got {difference.actual!r}",
            )
    print(
        f"--- {summary.passed}/{summary.case_count} passed "
        f"(failed {summary.failed}, errored {summary.errored}) "
        f"harness={summary.harness} provider={summary.provider}",
    )
    if args.out:
        print(f"summary -> {args.out}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pathfinder.devtools.evals")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("staged", help="list the candidates awaiting curation")
    sub.add_parser("extract", help="run one extraction pass now")
    sub.add_parser("corpus", help="list the promoted cases")

    show = sub.add_parser("show", help="show one candidate in full")
    show.add_argument("staging_id")

    promote = sub.add_parser("promote", help="write a candidate into the corpus")
    promote.add_argument("staging_id")
    promote.add_argument("--name", required=True, help="case name, also the file name")
    promote.add_argument("--rationale", required=True, help="what the case pins")
    promote.add_argument(
        "--turn",
        action="append",
        default=[],
        metavar="TEXT",
        help="override the request text; repeat once per turn, in order",
    )
    promote.add_argument(
        "--expect",
        default=None,
        metavar="JSON",
        help=(
            "the expectation as JSON, e.g. '{\"buildsStrategy\": false}'; "
            "defaults to what the recorded run did, which `show` prints; "
            "a disliked turn has no default and requires it"
        ),
    )
    promote.add_argument("--note", default="", help="curator note")

    run = sub.add_parser("run", help="run the corpus through the turn pipeline")
    run.add_argument("--only", nargs="*", default=[], metavar="NAME")
    run.add_argument("--out", default=None, metavar="FILE")
    run.add_argument(
        "--real",
        action="store_true",
        help=(
            "run against the configured provider instead of the deterministic "
            "one; needs WDK_DEV_EMAIL and WDK_DEV_PASSWORD"
        ),
    )
    run.add_argument(
        "--effort",
        choices=chat.EFFORTS,
        default=None,
        help="reasoning effort for every role (else each role's tier effort)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    route_framework_logs_to_stderr()
    args = _build_parser().parse_args(argv)
    if args.command == "staged":
        return asyncio.run(_list_staged())
    if args.command == "extract":
        return asyncio.run(_extract_now())
    if args.command == "corpus":
        return _list_corpus()
    if args.command == "show":
        return asyncio.run(_show(UUID(args.staging_id)))
    if args.command == "promote":
        return asyncio.run(_promote(args))
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
