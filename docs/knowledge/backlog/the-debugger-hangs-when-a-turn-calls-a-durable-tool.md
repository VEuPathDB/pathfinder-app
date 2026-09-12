---
type: Backlog
---

# The debugger hangs when a turn calls a durable tool

**What I did.** Ran the precise T. gondii invasion-protein prompt (cell-cycle similarity to MIC2 and RON2, signal peptide or 1 to 7 transmembrane domains, mass-spec evidence, a phyletic profile present in P. falciparum and absent from mammals) in the chat debugger inside the api container: `python -m pathfinder.devtools.chat run --site toxodb "<prompt>" --approve auto --quiet --run-dir /data/pf-runs/drive/t2/d4/turn1`, twice.

**What I got.** Both runs reached VERIFY, which called `run_control_tests_on_step`, and both logged `error Unknown tool error error_type=AppNotOpen tool_name=run_control_tests_on_step` (procrastinate's `AppNotOpen`: the debugger opens no job application). The first run then produced no further output for 47 minutes before I killed it; the second for 25 minutes, at 0% CPU, with no run artifacts at all: the run directory holds `run.log` and nothing else, so there is no `summary.json`, no `transcript.md`, no `events.jsonl` and no diagnosis to read.

**Why that's wrong.** The debugger is the tool for reading an agent's reasoning, and any precise prompt whose verification earns a control test wedges it. The run cannot be diagnosed afterwards because the artifacts are written at the end, and the time is lost silently: nothing says the run is stuck.

**Why it happens.** `pathfinder.devtools.chat` runs the graph in process with no procrastinate application, so a durable tool's `defer` raises `AppNotOpen`; the error is logged as an unknown tool error and the run neither fails nor completes.

**Fix.** The debugger declares up front that it cannot run durable tools: a durable call is answered with a refusal the agent can act on ("this tool runs on the worker and is not available in the debugger; report what you have"), written into the transcript as a tool result, so the turn finishes and the artifacts are written. The alternative, opening a real job application from the debugger, is a bigger change and is not what a reasoning debugger is for. Red first: a scripted turn whose VERIFY calls a durable tool ends with a written `summary.json` and a transcript line naming the refusal.

**What you'd get.** The run finishes in its usual few minutes, the artifacts are there, and the transcript says which durable tool was declined.
