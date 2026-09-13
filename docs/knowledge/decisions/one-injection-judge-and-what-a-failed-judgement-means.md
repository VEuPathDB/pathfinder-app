---
type: Decision
title: One injection judge, and what a failed judgement means
description: One ModelInjectionJudge serves both trust boundaries; the researcher's message fails closed with a 503 when the judge does not answer, and a tool result the judge could not read is withheld on its own so the turn survives. The judge is built at start and reported as the input_screening subsystem, and under the mock provider it runs on a scripted model that calls one marker string an injection. Failing open, a second judge, and per-call usage telemetry were rejected.
tags: [security, screening, readiness, testing, gates]
generated: { by: claude-code/opus-5, at: 2026-09-13T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-13T00:00:00Z }
status: stable
---

# What was decided

**One judge serves both boundaries.**
`apps/api/src/pathfinder/ai/capabilities/security.py` builds one
`ModelInjectionJudge` and hands it to the `UserInputScanner` the chat
dispatcher calls and to the `screened_output` scan the turn runner installs on
every tool source. A deployment that changes model changes one argument, and
the two boundaries never disagree about what an injection is.

**The suite screens, and it screens with a model that answers in process.**
Under `PATHFINDER_CHAT_PROVIDER=mock`, which the root `conftest.py` sets for the
whole suite, the judge's model is a `FunctionModel` that answers
`injection=true` for one text, `INJECTION_TEST_MARKER`, and `injection=false`
for everything else. Every test message and every tool result crosses the
boundary the deployment runs, no test downloads or loads anything, and no test
reaches a provider. A test that wants the refusal writes the marker into the
text; a test about the disabled path takes the `input_screening_disabled`
fixture from `tests/unit/conftest.py`.

**A message the judge did not read is refused, not passed.** A judgement is a
model call, so it can time out or meet an outage. `scan_user_input` answers a
`ScreeningRejectionError` with 403 `FORBIDDEN` and anything else with 503
`SERVICE_UNAVAILABLE`, titled "Screening is unavailable" and detailed
"Screening is unavailable. Send the message again in a moment." Neither answer
names the judge, its confidence or the provider behind it. The boundary exists
to keep unscreened text away from an agent that holds `delete_step`, so an
unread message does not become a turn.

**A tool result the judge did not read is withheld, and the turn survives.**
The scan never raises: a judge error is logged and answered with one fixed
sentence, "A result from this tool was not passed on because it could not be
screened." The tools already ran and the strategy is half built, so ending the
turn costs the researcher work that a second attempt cannot recover, while
losing one result costs a retry the model can make itself. This is the same
shape the runtime already uses for a result too long to read.

**Both processes build the judge at start, and each says so in its own way.**
`warm_up_screening()` builds it, and building it resolves the model name, so a
deployment that holds no credential for `INPUT_SCREENING_MODEL` finds out
before it serves anything. The api calls it first in the warm-up
(`main.py::_build_the_injection_judge`) and fails the `input_screening`
subsystem with the provider's own message, so `/health/ready` answers 503
before a researcher sends a message. The worker calls it first in `amain`
(`jobs/worker.py::_build_the_injection_judge`) and raises
`WorkerCannotScreenError` instead, because the worker serves no probe and every
tool result it reads crosses the judge: a worker that cannot screen would
withhold every result of every turn, so it consumes no jobs at all. Its log
line names both settings, and construction fails on configuration rather than
on a network, so a restart loop reports the fault rather than flapping around
it.

Both are gated by `input_screening_enabled`. A deployment that screens nothing
builds nothing and reports no such subsystem: `ReadinessState.input_screening`
stays `None`, and `not_ready` and `all_ready` skip it. An always-ready
subsystem would be noise; an absent one is a fact.

# Why

The boundary a suite skips is a boundary no test describes. The previous suite
turned screening off, because the classifier it ran was a 738 MB ONNX model: it
had to be downloaded at collection time, it held the CPU for seconds per
message, and its telemetry thread aborted the process at exit on macOS. Every
one of those costs belonged to the classifier, not to screening.

The classifier also had no failure mode worth deciding: it ran locally, so it
had no timeout, no provider and no outage. Replacing it with a model call adds
one, and a boundary that has not decided what its own failure means decides it
by accident, in whatever the framework does with an uncaught exception.

The marker is one fixed string rather than a list of phrases because a scripted
judge that guesses is a second, worse definition of an injection. The real
definition is the runtime's (`assistant-platform:
docs/knowledge/decisions/input-screening-is-configured-by-the-host.md`), and a
host does not restate it in a mock.

# What one judgement costs, and what is recorded

A judgement is one small call: about $0.00006 and roughly a second on the
runtime's own corpus. Every researcher message costs one in the api process,
and every tool result costs one per 30,000-character window in the worker.
`ModelInjectionJudge` builds its own agent, so those calls are outside the
turn's usage accounting and outside the cost bars the UI draws. That is
accepted at this price: what is recorded is one debug line per judgement,
carrying the number of characters judged and the elapsed seconds, which is what
an operator needs to see a slow provider. Wiring the judge into per-turn usage
would put a security boundary inside the accounting path for a term smaller
than the rounding on the bars it would feed.

The tool-result screen caches verdicts by the sha256 digest of the judged text.
`screened_output` builds one `VerdictCache` and `_screened_tool_output` is
`lru_cache(maxsize=1)`, so there is one cache per process, shared across every
user, conversation and turn, bounded at 1024 entries. It holds digests and
verdicts, never the text.

# What was rejected

**Failing open on the message boundary.** A logged warning and a turn that runs
anyway would make a provider outage the way past the screen, which is the one
thing an attacker can arrange from outside.

**Ending the turn when a tool result cannot be judged.** It is the strictest
answer and the most expensive one: the tools have already run, and the
researcher loses the build rather than one result.

**Keeping screening off for the suite.** It would leave `scan_user_input` and
the tool-result scan unexercised on every path but the tests that name them.

**A second judge, or a second context, for tool results.** One judge means one
definition, one model setting and one verdict cache.

**Letting the scripted judge read the runtime's own instructions.** The scripted
model receives the same prompt the real one does and ignores it. Making the mock
interpret that prompt would make the suite's verdicts depend on a heuristic
nothing else runs.

**Reporting `input_screening` as ready where the deployment screens nothing.**
`not_ready` is the list of things holding traffic back, and a subsystem that is
off holds nothing back.

# Anchor

`apps/api/src/pathfinder/tests/unit/ai/capabilities/test_security.py`: the
marker refused as a 403 that names neither the judge nor its confidence, a
product sentence passing, the marked tool result answered with the withheld
sentence, the benign one answered whole, the disabled setting building no
scanner, the 503 an outage answers, and the one result an outage withholds.
`.../tests/integration/chat/test_input_screening_refusal.py`: the 403 and the
503 over HTTP, each queueing no turn.
`.../tests/integration/http/test_tool_result_screen.py`: a served source whose
result carries the marker answered with the runtime's withheld sentence, and a
judge outage that loses one result while the turn finishes with no error chunk.
`.../tests/unit/platform/test_startup_binds_before_warm_up.py`: the judge built
at start, the subsystem failed with the provider's message when it cannot be,
and no subsystem at all where screening is off.
`.../tests/unit/jobs/test_worker_concurrency.py`: the worker building the judge
before it starts its heartbeat and its run, refusing to reach either when the
build fails, and building nothing where screening is off.
