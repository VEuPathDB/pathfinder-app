from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import structlog
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.conversation.event_stream import latest_turn_boundary
from assistant_core.graph.turn_state import (
    PendingApproval,
    PendingDurableCall,
    UserQuestionAnswer,
)
from assistant_core.mcp.admission import install_admitted_sources
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.models.capture import capture_llm
from assistant_core.persistence.models import ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.spec import AssistantSpec
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from sqlalchemy import select
from veupathdb.devtools.wdk_capture import capture_wdk
from veupathdb.wdk.auth_login import password_login

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.conversation.assistant_routing import resolve_turn_assistant
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.ai.conversation.turn_runner import TurnRequest, run_turn
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.devtools import inspector
from pathfinder.devtools.capture import RunCapture, capture_tracebacks, reset_run_dir
from pathfinder.devtools.gates import (
    BodyCtx,
    Gate,
    GateConsultQuestion,
    approval_body,
    consult_body,
    detect_gate,
    user_body,
)
from pathfinder.jobs.app import procrastinate_app
from pathfinder.jobs.auth_context import (
    attach_application,
    attach_user_id,
    attach_wdk_auth,
)
from pathfinder.jobs.payloads import ChatTurnPayload
from pathfinder.jobs.tasks import run_chat_turn_job
from pathfinder.persistence.repositories.background_tasks import (
    BackgroundTaskRepository,
)
from pathfinder.persistence.repositories.user import UserRepository
from pathfinder.platform.config import get_settings
from pathfinder.platform.tool_sources import admitted_tool_sources
from pathfinder.services.conversations.begin import begin_conversation

DEV_USER_ID = UUID("00000000-0000-0000-0000-0000000000c1")
RUN_ROOT = Path(os.environ.get("PF_RUN_ROOT", "/data/pf-runs"))
_MAX_RESUMES = 8


class RunArgs(BaseModel):
    prompt: str
    site: str
    mode: str = "strategy"
    conversation_id: UUID
    run_dir: Path
    mock: bool = False
    approve: Literal["prompt", "auto", "deny"] = "prompt"
    capture_wdk: bool = False
    capture_llm: bool = False
    via_worker: bool = False
    quiet: bool = False
    email: str | None = None
    password: str | None = None
    assistant: str | None = None
    phase_models: dict[PhaseRole, str] = {}


class RespondArgs(RunArgs):
    """Arguments for the respond subcommand, which answers a pending gate. There is
    no new user message, so the prompt field stays empty."""

    prompt: str = ""
    accept: bool = False
    deny: bool = False
    reason: str | None = None
    answers: list[str] = Field(default_factory=list)


class MissingCredentialsError(RuntimeError):
    pass


async def _wdk_token(args: RunArgs) -> str:
    """Resolves a real WDK auth token. Credentials come from the command line or
    the environment. Missing or rejected credentials raise."""

    email = args.email or os.environ.get("WDK_DEV_EMAIL")
    password = args.password or os.environ.get("WDK_DEV_PASSWORD")
    if not email or not password:
        msg = (
            "Login required for real runs. Set WDK_DEV_EMAIL and WDK_DEV_PASSWORD "
            "in .env.dev (and run with --env-file .env.dev), or pass "
            "--email/--password. Use --mock to skip login."
        )
        raise MissingCredentialsError(msg)
    token = await password_login(args.site, email, password)
    if not token:
        msg = f"WDK login failed for {email} on site {args.site!r} (bad credentials?)."
        raise MissingCredentialsError(msg)
    return token


async def _optional_wdk_token(args: RunArgs) -> str | None:
    """The WDK token for the run. Only the LLM is mocked, so a mocked run still
    logs in when credentials are there; without them it runs unauthenticated and
    pushes nothing to WDK."""
    if not args.mock:
        return await _wdk_token(args)
    if not (args.email or os.environ.get("WDK_DEV_EMAIL")):
        return None
    return await _wdk_token(args)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pathfinder.devtools.chat")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser(
        "run", help="execute one chat turn in-process, capturing artifacts"
    )
    run.add_argument("prompt")
    run.add_argument("--site", required=True)
    run.add_argument("--mode", default="strategy")
    run.add_argument("--conversation-id", default=None)
    run.add_argument("--run-dir", default=None)
    run.add_argument("--mock", action="store_true")
    run.add_argument("--approve", choices=["prompt", "auto", "deny"], default="prompt")
    run.add_argument("--capture-wdk", action="store_true")
    run.add_argument("--capture-llm", action="store_true")
    run.add_argument(
        "--via-worker",
        action="store_true",
        help="run the turn through the real worker (durable tools execute); "
        "LLM capture happens in the worker, events are replayed from the DB",
    )
    run.add_argument("--quiet", action="store_true")
    run.add_argument(
        "--email", default=None, help="WDK login email (else $WDK_DEV_EMAIL)"
    )
    run.add_argument(
        "--password", default=None, help="WDK login password (else $WDK_DEV_PASSWORD)"
    )
    run.add_argument(
        "--assistant",
        default=None,
        help="assistant id for a NEW conversation (else the registry default)",
    )
    run.add_argument("--model", action="append", default=[], metavar="PHASE=ID")

    resp = sub.add_parser(
        "respond",
        help="answer the conversation's pending gate (found via checkpoint)",
    )
    resp.add_argument("--site", required=True)
    resp.add_argument("--conversation-id", required=True)
    resp.add_argument("--run-dir", required=True)
    resp.add_argument("--mode", default="strategy")
    resp.add_argument("--mock", action="store_true")
    resp.add_argument("--approve", choices=["prompt", "auto", "deny"], default="prompt")
    resp.add_argument("--capture-wdk", action="store_true")
    resp.add_argument("--capture-llm", action="store_true")
    resp.add_argument("--via-worker", action="store_true")
    resp.add_argument("--quiet", action="store_true")
    resp.add_argument("--email", default=None)
    resp.add_argument("--password", default=None)
    resp.add_argument("--assistant", default=None)
    resp.add_argument("--model", action="append", default=[], metavar="PHASE=ID")
    resp.add_argument("--accept", action="store_true", help="approve the pending gate")
    resp.add_argument("--deny", action="store_true", help="deny the pending gate")
    resp.add_argument("--reason", default=None, help="reason for --deny")
    resp.add_argument(
        "--answer",
        action="append",
        default=[],
        metavar="QID=VALUE",
        help="consult answer (comma-separate VALUE for multi-choice)",
    )

    ins = sub.add_parser("inspect", help="read a captured run directory")
    ins.add_argument("run_dir")
    ins.add_argument("--failures", action="store_true")
    ins.add_argument("--anomalies", action="store_true")
    ins.add_argument("--tree", action="store_true")
    ins.add_argument("--tool", default=None)
    ins.add_argument("--llm", nargs="?", const="__all__", default=None, metavar="ROLE")

    diff = sub.add_parser(
        "diff", help="diff two captured runs to find the divergence point"
    )
    diff.add_argument("run_dir_a")
    diff.add_argument("run_dir_b")
    return p


def parse_run_args(argv: list[str]) -> RunArgs:
    ns = _build_parser().parse_args(["run", *argv])
    conv = UUID(ns.conversation_id) if ns.conversation_id else uuid4()
    turn_dir_name = uuid4().hex if ns.run_dir is None else ""
    run_dir = Path(ns.run_dir) if ns.run_dir else RUN_ROOT / str(conv) / turn_dir_name
    phase_models = dict(item.split("=", 1) for item in ns.model)
    return RunArgs.model_validate(
        {
            "prompt": ns.prompt,
            "site": ns.site,
            "mode": ns.mode,
            "conversation_id": conv,
            "run_dir": run_dir,
            "mock": ns.mock,
            "approve": ns.approve,
            "capture_wdk": ns.capture_wdk,
            "capture_llm": ns.capture_llm,
            "via_worker": ns.via_worker,
            "quiet": ns.quiet,
            "email": ns.email,
            "password": ns.password,
            "assistant": ns.assistant,
            "phase_models": phase_models,
        }
    )


def parse_respond_args(argv: list[str]) -> RespondArgs:
    ns = _build_parser().parse_args(["respond", *argv])
    phase_models = dict(item.split("=", 1) for item in ns.model)
    return RespondArgs.model_validate(
        {
            "site": ns.site,
            "mode": ns.mode,
            "conversation_id": UUID(ns.conversation_id),
            "run_dir": Path(ns.run_dir),
            "mock": ns.mock,
            "approve": ns.approve,
            "capture_wdk": ns.capture_wdk,
            "capture_llm": ns.capture_llm,
            "via_worker": ns.via_worker,
            "quiet": ns.quiet,
            "email": ns.email,
            "password": ns.password,
            "assistant": ns.assistant,
            "phase_models": phase_models,
            "accept": ns.accept,
            "deny": ns.deny,
            "reason": ns.reason,
            "answers": ns.answer,
        }
    )


def route_framework_logs_to_stderr() -> None:
    """Sends framework log output to stderr so stdout carries only the trace and the
    summary.

    The configuration is process-wide, so only a command line calls it.
    """

    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))


_VIA_WORKER_TIMEOUT_S = 1200
_VIA_WORKER_POLL_S = 3.0


def _body_ctx(args: RunArgs) -> BodyCtx:
    return BodyCtx(
        conversation_id=args.conversation_id,
        site_id=args.site,
        mode=args.mode,
        phase_models=args.phase_models,
    )


def _current_gate(capture: RunCapture) -> Gate:
    return detect_gate(
        pending_approval=capture.pending_approval,
        tool_args=capture.tool_args_by_call,
        durable_tasks=capture.durable_tasks,
    )


async def resolve_run_assistant(
    conversation_id: UUID,
    requested_id: str | None = None,
) -> AssistantSpec:
    """The thread's assistant, the requested one when the thread is new, or the
    default. A request naming another assistant than the thread's is refused."""
    return await resolve_turn_assistant(
        registry=get_assistant_registry(),
        conversation_id=conversation_id,
        requested_id=requested_id,
    )


async def _gate_from_checkpoint(
    conversation_id: UUID,
    settings_url: str,
    requested_id: str | None = None,
) -> Gate:
    """Derives the pending gate from the conversation checkpoint, which is the single
    source of truth for what the turn waits on."""
    registry = get_assistant_registry()
    spec = await resolve_run_assistant(conversation_id, requested_id)
    async with lifespan_checkpointer(
        settings_url,
        checkpoint_types=registry.checkpoint_types(),
    ) as saver:
        graph = spec.build_graph(saver)
        config: RunnableConfig = {"configurable": {"thread_id": str(conversation_id)}}
        snapshot = await graph.aget_state(config)
    values = snapshot.values or {}
    raw_durable = values.get("pending_durable_call")
    if raw_durable:
        parked = PendingDurableCall.model_validate(raw_durable)
        return detect_gate(
            pending_approval=None,
            tool_args={},
            durable_tasks=[
                (str(call.task_id), call.durable_tool_name)
                for call in parked.durable_calls
            ],
        )
    raw_pending = values.get("pending_approval")
    if not raw_pending:
        return Gate(kind="none", message="turn complete")
    pending = PendingApproval.model_validate(raw_pending)
    return detect_gate(
        pending_approval=(pending.tool_name, pending.tool_call_id),
        tool_args={pending.tool_call_id: dict(pending.tool_args)},
        durable_tasks=[],
    )


def _write_gate(run_dir: Path, gate: Gate) -> None:
    (run_dir / "gate.json").write_text(gate.model_dump_json(indent=2, by_alias=True))


def _auto_answer(q: GateConsultQuestion) -> UserQuestionAnswer:
    chosen = [o.label for o in q.options if o.recommended]
    if not chosen and q.options:
        chosen = [q.options[0].label]
    return UserQuestionAnswer(
        question_id=q.id,
        prompt=q.prompt,
        chosen_labels=chosen,
        note="" if chosen else "proceed with defaults",
    )


def _auto_respond(
    args: RunArgs, gate: Gate, message_id: UUID
) -> ChatRequestBody | None:
    """Builds the automatic reply to a gate. None stops at the gate so the operator
    answers it."""
    if gate.kind in {"none", "durable"} or args.approve not in {"auto", "deny"}:
        return None
    if gate.kind == "consult":
        if args.approve == "deny" or gate.tool_call_id is None:
            return None
        return consult_body(
            _body_ctx(args),
            message_id=message_id,
            tool_call_id=gate.tool_call_id,
            answers=[_auto_answer(q) for q in gate.consult_questions],
        )
    if (
        gate.kind == "approval"
        and gate.tool is not None
        and gate.tool_call_id is not None
    ):
        approved = args.approve == "auto"
        return approval_body(
            _body_ctx(args),
            message_id=message_id,
            tool=gate.tool,
            tool_call_id=gate.tool_call_id,
            approved=approved,
            reason=None if approved else "auto-deny",
        )
    return None


async def _exec_one(
    args: RunArgs,
    capture: RunCapture,
    body: ChatRequestBody,
    *,
    settings_url: str,
    wdk_token: str | None,
) -> None:
    """Runs one body until it completes or reaches a gate, in process or in the worker."""
    if args.via_worker:
        await _exec_via_worker(args, capture, body, wdk_token=wdk_token)
        return
    async with AsyncExitStack() as stack:
        if args.capture_wdk:
            await stack.enter_async_context(capture_wdk(capture.run_dir))
        if args.capture_llm:
            stack.enter_context(capture_llm(capture.run_dir))
        await stack.enter_async_context(attach_wdk_auth(wdk_token))
        await stack.enter_async_context(attach_user_id(DEV_USER_ID))
        # The debugger drives the turn itself, so it admits what the worker does.
        install_admitted_sources(admitted_tool_sources())
        registry = get_assistant_registry()
        spec = await resolve_run_assistant(body.conversation_id, args.assistant)
        saver = await stack.enter_async_context(
            lifespan_checkpointer(
                settings_url,
                checkpoint_types=registry.checkpoint_types(),
            ),
        )
        store = await stack.enter_async_context(lifespan_memory_store(settings_url))
        graph = spec.build_graph(saver)
        await run_turn(
            request=TurnRequest(body=body, user_id=DEV_USER_ID),
            spec=spec,
            compiled_graph=graph,
            memory_store=store,
            writer=capture,
        )


async def _defer_chat_turn(payload: ChatTurnPayload) -> None:
    """Defer one turn under the conversation's lock, as the API route does."""
    async with procrastinate_app.open_async():
        await run_chat_turn_job.configure(
            lock=str(payload.body.conversation_id),
        ).defer_async(
            payload=payload.model_dump(mode="json", by_alias=True),
        )


async def _worker_payload(
    args: RunArgs,
    capture: RunCapture,
    body: ChatRequestBody,
    *,
    wdk_token: str | None,
) -> ChatTurnPayload:
    """The job the worker runs. It names the assistant the thread is served by."""
    spec = await resolve_run_assistant(args.conversation_id, args.assistant)
    return ChatTurnPayload(
        body=body,
        user_id=DEV_USER_ID,
        turn_id=capture.turn_id,
        veupathdb_auth_token=wdk_token,
        capture_dir=str(args.run_dir),
        assistant_id=spec.assistant_id,
    )


async def _exec_via_worker(
    args: RunArgs, capture: RunCapture, body: ChatRequestBody, *, wdk_token: str | None
) -> None:
    """Defers a real chat turn job to the worker, reports task progress while it runs,
    then replays the persisted events."""
    before = await latest_turn_boundary(args.conversation_id)
    payload = await _worker_payload(args, capture, body, wdk_token=wdk_token)
    await _defer_chat_turn(payload)
    if not args.quiet:
        print("deferred to worker; waiting…")

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    deadline = time.monotonic() + _VIA_WORKER_TIMEOUT_S
    seen_progress: set[str] = set()
    while time.monotonic() < deadline:
        await asyncio.sleep(_VIA_WORKER_POLL_S)
        boundary = await latest_turn_boundary(args.conversation_id)
        active = await repo.list_active_for_conversation(
            conversation_id=args.conversation_id
        )
        if not args.quiet:
            for task in active:
                line = f"  ⏳ task {task.tool_name} [{task.status}]"
                if line not in seen_progress:
                    seen_progress.add(line)
                    print(line)
        if boundary > before and not active:
            break

    async with async_session_factory() as session:
        rows = await session.scalars(
            select(ConversationEvent)
            .where(
                ConversationEvent.conversation_id == args.conversation_id,
                ConversationEvent.id > before,
            )
            .order_by(ConversationEvent.id),
        )
        for row in rows:
            await capture.write(row.chunk)


async def _drive_conversation(
    args: RunArgs,
    capture: RunCapture,
    body: ChatRequestBody,
    *,
    settings_url: str,
    wdk_token: str | None,
) -> Gate:
    """Runs the body, then answers gates automatically until a gate needs the operator
    or the turn completes. Returns the final pending gate."""
    for _ in range(_MAX_RESUMES):
        capture.turn_id = uuid4()
        await _exec_one(
            args, capture, body, settings_url=settings_url, wdk_token=wdk_token
        )
        gate = _current_gate(capture)
        next_body = _auto_respond(args, gate, uuid4())
        if next_body is None:
            return gate
        body = next_body
    return _current_gate(capture)


async def _replay_run_dir(capture: RunCapture, run_dir: Path) -> None:
    """Rebuilds the capture state from a prior step's event log, so the next step keeps
    the full conversation context and the pending gate."""
    events_path = run_dir / "events.jsonl"
    if not events_path.is_file():
        return
    was_quiet = capture.quiet
    capture.quiet = True
    try:
        for line in events_path.read_text().splitlines():
            if line.strip():
                await capture.write(json.loads(line))
    finally:
        capture.quiet = was_quiet


async def drive_run(args: RunArgs) -> tuple[RunCapture, Gate]:
    """Run one prompt to completion or to a gate, and return the capture.

    The eval runner reads the capture; the command line prints it.
    """
    async with attach_application():
        if args.mock:
            os.environ["PATHFINDER_CHAT_PROVIDER"] = "mock"
            os.environ["API_ENV"] = "test"
            get_settings.cache_clear()
        settings = get_settings()

        wdk_token = await _optional_wdk_token(args)
        if not args.quiet and wdk_token is not None:
            print(f"logged in as {args.email or os.environ.get('WDK_DEV_EMAIL')}")

        spec = await resolve_run_assistant(args.conversation_id, args.assistant)
        async with async_session_factory() as session:
            await UserRepository(session).get_or_create(DEV_USER_ID)
            await begin_conversation(
                session=session,
                conversation_id=args.conversation_id,
                user_id=DEV_USER_ID,
                site_id=args.site,
                assistant_id=spec.assistant_id,
            )
            await session.commit()

        capture = RunCapture(
            conversation_id=args.conversation_id,
            turn_id=uuid4(),
            run_dir=args.run_dir,
            quiet=args.quiet,
        )
        reset_run_dir(args.run_dir)
        if not args.quiet:
            print(f"conversation={args.conversation_id}")
            print(f"run-dir={args.run_dir}")

        body = user_body(_body_ctx(args), message_id=capture.turn_id, text=args.prompt)
        with capture_tracebacks(args.run_dir):
            gate = await _drive_conversation(
                args,
                capture,
                body,
                settings_url=settings.database_url,
                wdk_token=wdk_token,
            )

        capture.flush()
        _write_gate(args.run_dir, gate)
        return capture, gate


async def run_once(args: RunArgs) -> int:
    capture, gate = await drive_run(args)
    _report(capture, gate)
    return 1 if capture.has_error else 0


class GateResponseError(RuntimeError):
    pass


def _parse_answer(raw: str, gate: Gate) -> UserQuestionAnswer:
    qid, _, value = raw.partition("=")
    question = next((q for q in gate.consult_questions if q.id == qid), None)
    prompt = question.prompt if question is not None else ""
    if question is not None and question.kind == "free_text":
        return UserQuestionAnswer(
            question_id=qid, prompt=prompt, chosen_labels=[], note=value
        )
    labels = [v.strip() for v in value.split(",") if v.strip()]
    return UserQuestionAnswer(question_id=qid, prompt=prompt, chosen_labels=labels)


def _build_respond_body(args: RespondArgs, gate: Gate) -> ChatRequestBody:
    mid = uuid4()
    if gate.kind == "none" or gate.tool_call_id is None:
        msg = "no pending gate to respond to"
        raise GateResponseError(msg)
    if args.answers:
        return consult_body(
            _body_ctx(args),
            message_id=mid,
            tool_call_id=gate.tool_call_id,
            answers=[_parse_answer(a, gate) for a in args.answers],
        )
    if args.deny or args.accept:
        if gate.tool is None:
            msg = "gate has no approvable tool"
            raise GateResponseError(msg)
        return approval_body(
            _body_ctx(args),
            message_id=mid,
            tool=gate.tool,
            tool_call_id=gate.tool_call_id,
            approved=args.accept and not args.deny,
            reason=args.reason if args.deny else None,
        )
    msg = "nothing to respond — pass --accept / --deny / --answer"
    raise GateResponseError(msg)


async def run_respond(args: RespondArgs) -> int:
    async with attach_application():
        if args.mock:
            os.environ["PATHFINDER_CHAT_PROVIDER"] = "mock"
            os.environ["API_ENV"] = "test"
            get_settings.cache_clear()
        settings = get_settings()
        wdk_token = await _optional_wdk_token(args)

        spec = await resolve_run_assistant(args.conversation_id, args.assistant)
        async with async_session_factory() as session:
            await UserRepository(session).get_or_create(DEV_USER_ID)
            await begin_conversation(
                session=session,
                conversation_id=args.conversation_id,
                user_id=DEV_USER_ID,
                site_id=args.site,
                assistant_id=spec.assistant_id,
            )
            await session.commit()

        capture = RunCapture(
            conversation_id=args.conversation_id,
            turn_id=uuid4(),
            run_dir=args.run_dir,
            quiet=args.quiet,
        )
        await _replay_run_dir(capture, args.run_dir)
        gate = await _gate_from_checkpoint(
            args.conversation_id,
            settings.database_url,
            args.assistant,
        )
        if gate.kind == "none":
            gate = _current_gate(capture)
        if gate.kind == "none":
            print("no pending gate to respond to (turn already complete)")
            return 0
        body = _build_respond_body(args, gate)

        with capture_tracebacks(args.run_dir):
            final_gate = await _drive_conversation(
                args,
                capture,
                body,
                settings_url=settings.database_url,
                wdk_token=wdk_token,
            )

        capture.flush()
        _write_gate(args.run_dir, final_gate)
        _report(capture, final_gate)
        return 1 if capture.has_error else 0


def _report(capture: RunCapture, gate: Gate) -> None:
    summary = capture.summary()
    anomalies = capture.anomalies()
    print(
        f"─── summary ───  status={summary.status}  tokens={summary.tokens}  "
        f"cost=${summary.cost_usd:.3f}  toolcalls={summary.tool_calls}  "
        f"failures={summary.failures}  loop={str(summary.loop_detected).lower()}  "
        f"anomalies={len(anomalies)}"
    )
    for anomaly in anomalies:
        print(f"  ⚑ [{anomaly.severity}] {anomaly.kind}: {anomaly.message}")
    print(f"─── gate ───  {gate.kind}: {gate.message}")
    if gate.kind == "consult":
        for q in gate.consult_questions:
            opts = " | ".join(
                f"{o.label}{'*' if o.recommended else ''}" for o in q.options
            )
            print(f"  ? [{q.id}] {q.prompt}  ({opts})")
    print(f"run-dir={summary.run_dir}")


def _run_inspect(ns: argparse.Namespace) -> int:
    run_dir = Path(ns.run_dir)
    if ns.llm is not None:
        role = None if ns.llm == "__all__" else ns.llm
        print(inspector.render_llm(run_dir, role))
    elif ns.tool:
        print(inspector.render_tool(run_dir, ns.tool))
    elif ns.anomalies:
        print(inspector.render_anomalies(run_dir))
    elif ns.tree:
        print(inspector.render_tree(run_dir))
    else:
        print(inspector.render_failures(run_dir))
    return 0


def main() -> None:
    route_framework_logs_to_stderr()
    argv = sys.argv[1:]
    command = argv[0] if argv else ""
    if command == "run":
        try:
            sys.exit(asyncio.run(run_once(parse_run_args(argv[1:]))))
        except MissingCredentialsError as exc:
            print(f"✖ {exc}", file=sys.stderr)
            sys.exit(2)
    if command == "respond":
        try:
            sys.exit(asyncio.run(run_respond(parse_respond_args(argv[1:]))))
        except (MissingCredentialsError, GateResponseError) as exc:
            print(f"✖ {exc}", file=sys.stderr)
            sys.exit(2)
    ns = _build_parser().parse_args(argv)
    if ns.command == "inspect":
        sys.exit(_run_inspect(ns))
    if ns.command == "diff":
        print(inspector.render_diff(Path(ns.run_dir_a), Path(ns.run_dir_b)))
        sys.exit(0)


if __name__ == "__main__":
    main()
