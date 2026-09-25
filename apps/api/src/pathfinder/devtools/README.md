# `pathfinder.devtools.chat` - chat pipeline debugger

An in-process debugger for the PathFinder chat pipeline, built for **agents** to
drive. It runs one chat turn through the real `run_turn` (same code path the
worker uses) **without** the API server, worker, procrastinate, or SSE - then
captures every plane of the run to flat files you can `cat`/`jq` and runs a
diagnosis pass that names known failure modes for you.

Use it to reproduce and localize chat/agent bugs (phase routing, tool-call
loops, validation failures, token blowups, WDK disagreements) without clicking
through the UI or re-running turns to "see more."

---

## Run it (inside the api container)

The DB is reachable inside the container as `db:5432`. On the host, port 5432 is
squatted by a non-docker postgres, so **always run via `docker compose exec api`**.

```bash
docker compose exec -T api .venv/bin/python -m pathfinder.devtools.chat run \
  "Which OBPs are most highly female-adult enriched in Aedes aegypti?" \
  --site vectorbase \
  --approve auto \
  --capture-wdk \
  --quiet \
  --run-dir /data/pf-runs/obp/turn1 \
  --model lead=openai:gpt-5.6-luna \
  --model frame=openai:gpt-5.6-luna \
  --model execution=openai:gpt-5.6-luna \
  --model verification=openai:gpt-5.6-luna
```

stdout is a clean compact trace + a final summary line with the run-dir path.
Framework logs go to **stderr** (redirect with `2>/dev/null` if you don't want
them). The summary prints any anomalies inline:

```
─── summary ───  status=ok  tokens=555763  cost=$0.206  toolcalls=43  failures=12  loop=true  anomalies=2
  ⚑ [critical] loop: frame_problem failed 5 times - the agent is stuck retrying.
  ⚑ [warning] budget_burn: 555763 tokens ($0.21) - abnormally high.
run-dir=/data/pf-runs/obp/turn2
```

### Artifacts land on the HOST

`/data/pf-runs` in the container is bind-mounted to `apps/api/.pf-runs` on the
host (gitignored). So after a run you read the artifacts directly:

```bash
jq -r '.[] | "[\(.severity)] \(.kind): \(.message)"' apps/api/.pf-runs/obp/turn2/diagnosis.json
jq -r '.status, (.errors|map(.kind+":"+(.param//"?")))' apps/api/.pf-runs/obp/turn2/tools/28-frame_problem.json
```

No DB and no re-run needed to inspect a past run - the files are the interface.

---

## `run` flags

| flag | meaning |
|------|---------|
| `prompt` (positional) | the user message for this turn |
| `--site` | WDK site id (e.g. `vectorbase`, `plasmodb`) - required |
| `--conversation-id <uuid>` | resume an existing conversation (durable via checkpointer). Omit to mint a new one (printed unless `--quiet`). |
| `--run-dir <path>` | where artifacts go. Default `/data/pf-runs/<conv>/<turn>`. Re-using a path is safe - each run **resets** the artifact subdirs (`tools/`, `state/`, `errors/`, `wdk/`) and top-level files first, so two runs never mix. Other files in the directory are left alone. |
| `--model PHASE=ID` | per-phase model override (repeatable). Phases: `lead frame execution verification`. |
| `--effort none\|low\|medium\|high` | reasoning effort for every role, sent as the request body's `phaseReasoning` the way the settings panel sends it. Omit it and each role runs at its tier's effort. `respond` takes it too, so a resumed gate keeps the effort. The run directory records it in `turn_settings.json`. |
| `--attach PATH` | attach a local file to the message (repeatable), inline as a `file` part, the way the composer attaches one. The chat route's refusal applies: a kind the Lead's model does not read, or a file over 10 MB, is refused before the turn. |
| `--approve auto\|deny\|prompt` | how to answer mid-turn approval gates (`consult_user`, etc.). `auto` for unattended; `prompt` reads stdin. |
| `--capture-wdk` | also record raw WDK httpx round-trips to `wdk/`. |
| `--via-worker` | run the turn through the **real worker** (defers a `chat_turn:run` job) instead of in-process, so **durable tools actually execute** (enrichment, control tests, optimization) and verification can complete. The worker writes `llm/` to the shared run-dir (captures the durable resumes too - the post-result phase agents); the devtool waits for the turn to settle, then replays the persisted `conversation_events` into `events.jsonl`/`tools/`/`diagnosis`. Use this whenever the in-process run can't finish because a durable tool raises (the `AppNotOpen`/stub case). Requires the worker container running. |
| `--capture-llm` | (in-process runs) record the exact LLM I/O per call to `llm/NN-<role>-{request,response}.json` - the full system prompt (`instructions`), the complete typed message history **as the model receives it** (incl. `tool-return` / `retry-prompt` parts - i.e. whether the model actually sees an error/directive), the tool definitions offered, model settings, and the response parts + usage + finish reason. The ground-truth plane for "does the model truly see X". Read with `inspect <dir> --llm [role]`. |
| `--mock` | use the deterministic FunctionModel (free; also sets `API_ENV=test`). Default is the real configured provider. |
| `--email` / `--password` | WDK login override; default to `WDK_DEV_EMAIL` / `WDK_DEV_PASSWORD` (set in `.env.dev`). |
| `--assistant <id>` | which assistant to run. It applies when the thread is new; naming another assistant than an existing thread's is refused. Default: the registry's default. |
| `--quiet` | suppress the live trace; still writes artifacts + prints the summary. |

**Login is mandatory for real runs.** A non-mock `run` logs in to VEuPathDB as the
dev user (creds from `WDK_DEV_EMAIL`/`WDK_DEV_PASSWORD` in `.env.dev`, or
`--email`/`--password`) and runs all WDK calls as that authenticated user. If the
creds are missing or rejected it aborts with a clear error. `--mock` skips login
(it never touches WDK). This requires running compose with `--env-file .env.dev`
so the vars reach the container.

## Driving gates like the UI (`run` + `respond`)

The CLI mirrors every action the chat UI offers, agent-style. After each step it
detects the one pending interaction and writes **`gate.json`** (+ prints it):

| gate `kind` | UI equivalent | how to answer |
|------|------|------|
| `approval` | approval card (`consult_user`, `delete_step`, ...) | `respond ... --accept` / `--deny [--reason ...]` |
| `consult` | question carousel (`consult_user`) | `respond ... --answer <qid>=<label>` (repeat; comma-separate for multi) |
| `approval` w/ `plan_slots` | plan slot form (NEEDS_USER_INPUT) | `respond ... --slot <stepId>:<param>=<value>` (repeat) |
| `durable` | running background task | nothing - `--via-worker` streams progress and continues |
| `none` | turn complete | - |

```bash
# one turn; stops at the first gate (default --approve prompt) and writes gate.json
... chat run "<prompt>" --site vectorbase --conversation-id <uuid> --run-dir <dir>
jq . <dir>/gate.json          # read what's pending (questions/options/slots)

# answer it (same --run-dir continues the conversation)
... chat respond --site vectorbase --conversation-id <uuid> --run-dir <dir> \
    --answer strain_choice="Liverpool (default/recommended)"
# ...repeat run/respond until gate.kind == "none"
```

`--approve auto` autopilots through gates (approves, picks recommended consult
options) until completion or a gate it can't auto-answer. `--approve deny` denies
approvals. Both `run` and `respond` honor `--via-worker` (durable tools execute in
the worker) and `--capture-llm`.

**Multi-turn - STRICTLY one turn at a time. NEVER batch turns.** This is a real
conversation: you do not know what the agent will say until it says it. The agent
routinely asks clarifying questions, presents decision forks, or reports partial
results, and your next message must answer *what it actually asked* - not what you
guessed it would ask.

The required loop is:
1. Run **one** turn.
2. **Read** the assistant's final message and artifacts (`jq -r 'select(.type=="text-delta").delta' .../events.jsonl`, plus `summary.json`/`diagnosis.json`).
3. Compose the next turn as a genuine reply to that message.
4. Run the next turn with `--conversation-id <same>`. Repeat.

**Do NOT** chain turn 1 and turn 2 in one shell invocation with a pre-written
turn-2 reply. If you find yourself writing the next prompt before reading the last
response, stop - you are guessing, and the run is invalid. There is no REPL (agents
can't feed stdin to a live process); durable resume via `--conversation-id` is the
equivalent and is what you should use, one step at a time.

Exit code is non-zero when the turn ends on a terminal `error` chunk.

---

## Inspecting a run

The flat files are grep/jq-friendly, but `inspect` adds cross-plane correlation
that raw shell can't do trivially. Run it anywhere the files are reachable
(in-container against `/data/pf-runs/...`, or on the host against
`apps/api/.pf-runs/...`):

```bash
# every failed tool: args + decoded errors + traceback, correlated
... chat inspect <run-dir> --failures

# every attempt of one tool, args diffed across attempts (surfaces oscillation)
... chat inspect <run-dir> --tool frame_problem

# the diagnosis (anomalies, most severe first)
... chat inspect <run-dir> --anomalies

# the span tree (shape: phases -> tool calls, with durations)
... chat inspect <run-dir> --tree

# divergence point between a failing and a passing run
... chat diff <run-dir-a> <run-dir-b>
```

---

## Run directory layout

```
<run-dir>/
  summary.json        # shape + headline counts + pointers
                      # toolcalls = every call the log announces, whether the
                      # turn ran one agent or a Lead with sub-agents
  diagnosis.json      # detected anomalies (see below)
  events.jsonl        # every chunk, raw, untruncated - the SSOT
  tools/NN-<tool>.json# per tool call: phase, FULL args, status, FULL result,
                      #   decoded validation errors, duration
  tree.{json,txt}     # turn -> phase -> tool-call span tree
  state/<phase>.json  # ledger + problem-frame snapshot at each phase boundary
  errors/NN-*.txt     # Python tracebacks for any logged exception
  wdk/NN-*.json       # raw WDK request/response (only with --capture-wdk)
  transcript.md       # human-readable trace
  turn_settings.json  # assistant id, phaseModels and phaseReasoning the run sent
                      # ({} means each role at its tier's default)
```

`tools/*.json` is the substrate for surgical debugging: display in stdout is
clipped, but **disk keeps full args and full results** (e.g. the complete
`frame_problem` payload that failed), with Pydantic/`VALIDATION_ERROR`/"unknown
keys" failure strings decoded into a typed `errors[]` list (`kind`, `param`,
`search_name`).

---

## Diagnosis fingerprints (`diagnosis.json`)

The engine (`diagnosis.py`) flags PathFinder's recurring failure modes:

| kind | meaning |
|------|---------|
| `validation_catch_22` | a param is **required by one validator but rejected as unknown by another** - unsatisfiable. This is the `document_type` bug's exact signature. |
| `loop` | one tool failed ≥5 times (consecutive or alternating error signatures) - the agent is stuck. |
| `wdk_service_error` | the same search returned a WDK 5xx ≥2 times - the agent retried an unavailable search instead of routing around it. Usually an upstream outage, not a PathFinder bug. |
| `silent_zero` | a step returned 0 results (`ledger.build.zeroResultSteps`) **and the reply never said so** - possible silent failure (e.g. missing JSESSIONID, wrong params). |
| `silent_constraint_violation` | a user-explicit constraint was substituted or ungroundable, blocking, **and the reply never named it** - the plan deviated from what the user asked without saying so. |
| `budget_burn` | the turn consumed an abnormal number of tokens (≥200k). |
| `no_plan` | planning terminated without producing a plan. |

**The `silent_*` kinds read the reply, not just the ledger.** Their claim is that the turn never surfaced the problem, and a Lead usually surfaces it in prose, which no structured ledger field records. `transcript.md` carries the reply under `## Reply` so you can check the call yourself. A run captured without any reply text counts as silent, so an uncaptured run is never quietly excused.

---

## Gotchas

- **Run in the container, not the host** (host DB port conflict).
- **Durable tools** (`run_control_tests_on_step`, `optimize_search_parameters`,
  enrichment) call procrastinate, which isn't open in-process - they raise
  `AppNotOpen`. The traceback is captured, but those tools can't fully execute
  here. Use the full stack to debug them.
- **State snapshots are chunk-derived** (reconstructed from ledger/problem-frame
  chunks), not read from live `agent_state`.
- **Editing the devtool?** Rebuild with the env file or settings validation
  crashes the container:
  `docker compose --env-file .env.dev up -d --build --force-recreate api worker`
- Tests: `apps/api/src/pathfinder/tests/{unit,integration}/devtools/`.

---

## `pathfinder.devtools.evals` - the curation desk and the eval run

The same turn pipeline, driven from the corpus instead of from a prompt. It
shares `chat.py`'s `drive_run`, so a case runs exactly as a chat turn does, and
its artifacts land under `/data/pf-runs/evals/<case-name>/turn-<n>/` where
`inspect` reads them. A case states `turns`, a list driven in order on one
conversation id, so an edit case is one file with two entries.

```bash
docker compose --env-file .env.dev exec -T api uv run python -m pathfinder.devtools.evals staged
docker compose --env-file .env.dev exec -T api uv run python -m pathfinder.devtools.evals show <staging-id>
docker compose --env-file .env.dev exec -T api uv run python -m pathfinder.devtools.evals promote <staging-id> \
  --name a-case-name --rationale "what this pins" --expect '{"buildsStrategy": false}'
  # --turn "first message" --turn "second message" overrides the staged requests
docker compose --env-file .env.dev exec -T api uv run python -m pathfinder.devtools.evals corpus
docker compose --env-file .env.dev exec -T api uv run python -m pathfinder.devtools.evals run \
  --out /data/pf-runs/evals/summary.json
```

`extract` runs one extraction pass by hand; the worker runs it daily on the
`maintenance` queue.

**A run under the deterministic provider tests the pipeline, not the model.**
The mock is a script that routes on keywords, so a green run says the routing,
the materialisation, the persistence and the reported verdict still behave. The
corpus is provider-agnostic: a real-model run is the same command with a
different provider (`--real`), and `--effort none|low|medium|high` runs every
role of every case at one effort, as the chat debugger's flag does.

---

## Modules

| file | responsibility |
|------|----------------|
| `chat.py` | CLI: `run`/`respond`/`inspect`/`diff`, bootstrap, turn loop, approval resume |
| `evals.py` | CLI: `staged`/`show`/`promote`/`corpus`/`extract`/`run` |
| `eval_runner.py` | one case per fresh thread, every turn in order, read back from the projection and the checkpoint |
| `capture.py` | `RunCapture` (chunk -> artifacts writer) + `capture_tracebacks` |
| `models.py` | artifact schema + chunk parsers + validation-error decoder |
| `diagnosis.py` | the fingerprint engine |
| `inspector.py` | `inspect`/`diff` rendering (pure, reads a run-dir) |
| `veupathdb.devtools.wdk_capture` | opt-in WDK httpx capture (`--capture-wdk`) |
| `gates.py` | the gate the CLI detects after a step, and the parts `respond` sends to answer it |
| `openapi.py` | CLI: `generate`/`check` for `packages/spec/openapi.{json,yaml}` |
| `wdk_fixtures.py` | CLI: `list`/`record`/`verify`/`vendor` for the WDK fixtures the tests replay and the pinned WDK schemas `verify` reads |
| `eda_schemas.py` | CLI: `types`/`verify`/`vendor` for the pinned `service-eda` RAML type library the recorded EDA bodies answer to |

`wdk_fixtures verify` needs no network and no credential. It validates every recorded
fixture body against the WDK schema its endpoint annotates, using the copy vendored under
`veupathdb.testing.fixtures/wdk/schema/` at the commit `schema-pin.json` names, and it
fails when a vendored file no longer matches the sha256 the pin records. `vendor`
re-downloads that tree at the pinned commit, deletes what the `$ref` closure no longer
reaches, and rewrites the pin only when a byte changed; bump the `sha` field first, then
run it. Only the schemas WDK actually enforces are pinned, which is a small
part of the tree: see `docs/knowledge/wdk/rules/auth-and-transport.md` (WDK-HTTP-004).

`eda_schemas verify` needs no network and no credential either. It converts the RAML 1.0
type library `VEuPathDB/service-eda` publishes to JSON Schema draft-07 and validates every
recorded EDA body under `src/pathfinder/tests/unit/integrations/eda/fixtures/` against the
type its endpoint returns, reading the copy vendored under that directory's `upstream/` at
the commit `schema-pin.json` names. Ten specification defects are declared and excluded, each
measured: see `docs/knowledge/eda/rest-surface.md`. `vendor` re-downloads the library and its
one include at the pinned commit and rewrites the pin only when a byte changed; bump the
`sha` field first, then run it.

`RunCapture` implements the `ChatWriter` protocol
(`assistant_core.conversation.event_writer`) - the same surface as the production
`ChatEventWriter`, so the CLI exercises the real turn pipeline.
