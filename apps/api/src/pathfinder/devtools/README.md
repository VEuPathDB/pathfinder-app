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
─── summary ───  status=ok  tokens=555763  cost=$0.206  toolcalls=43  failures=12  loop=true  assumed=0  anomalies=2
  ⚑ [critical] loop: frame_problem failed 5 times in a row (3 distinct error signatures) - the agent is stuck retrying.
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
| `--sites <file>` | the sites file the turn reads. Without it the run reads `$VEUPATHDB_SITES_CONFIG`, and without that the QA sites (`deploy/sites/qa.yml`, `/app/config/sites/qa.yml` in the image), never the client's bundled production list. With `--via-worker` the file must be the one the worker reads (the stack's `VEUPATHDB_SITES_CONFIG`); a worker on the bundled list, or on another file, refuses the run with exit code 2. `respond` takes it too. |
| `--conversation-id <uuid>` | resume an existing conversation (durable via checkpointer). Omit to mint a new one (printed unless `--quiet`). |
| `--run-dir <path>` | where artifacts go. Default `/data/pf-runs/<conv>/<turn>`. Re-using a path is safe - each run **resets** the artifact subdirs (`tools/`, `state/`, `errors/`, `wdk/`, `llm/`) and top-level files first, so two runs never mix. Other files in the directory are left alone. |
| `--model PHASE=ID` | per-phase model override (repeatable). Phases: `lead frame execution verification`. |
| `--effort none\|low\|medium\|high` | reasoning effort for every role, sent as the request body's `phaseReasoning` the way the settings panel sends it. Omit it and each role runs at its tier's effort. `respond` takes it too, so a resumed gate keeps the effort. The run directory records it in `turn_settings.json`. |
| `--attach PATH` | attach a local file to the message (repeatable), inline as a `file` part, the way the composer attaches one. The chat route's refusal applies: a kind the Lead's model does not read, or a file over 10 MB, is refused before the turn. |
| `--approve auto\|deny\|prompt` | how to answer mid-turn approval gates (`consult_user`, etc.). `auto` for unattended; `prompt` reads stdin. |
| `--capture-wdk` | also record raw WDK httpx round-trips to `wdk/`. |
| `--via-worker` | run the turn through the **real worker** (defers a `chat_turn:run` job) instead of in-process, so **durable tools actually execute** (enrichment, control tests, optimization) and verification can complete. The worker writes its `llm/` capture (the durable resumes too - the post-result phase agents) under `/data/pf-runs/.worker-llm/<turn>`, the compose mount it shares with `apps/api/.pf-runs`, and the devtool moves it into `<run-dir>/llm/` after the turn, so any `--run-dir` works; a capture that never arrives is reported on stderr. The devtool follows the thread's log (`turn_arc.py`) until the turn ends: a turn that parks on a durable task prints `turn parked on <tool>` and the devtool keeps waiting through the completion turn the task opens, as the web client does, then replays the chat stream into `events.jsonl`/`tools/`/`diagnosis`. The run ends at a turn that wrote its `done` without parking, or at a stopped turn. Use this whenever the in-process run can't finish because a durable tool raises (the `AppNotOpen`/stub case). Requires the worker container running. |
| `llm/` (always) | every run records the exact LLM I/O per call to `llm/NN-<role>-{request,response}.json` - the full system prompt (`instructions`), the complete typed message history **as the model receives it** (incl. `tool-return` / `retry-prompt` parts - i.e. whether the model actually sees an error/directive), the tool definitions offered, model settings, and the response parts + usage + finish reason. The ground-truth plane for "does the model truly see X". Read with `inspect <dir> --llm [role]`. |
| `--mock` | use the scripted model (free; also sets `API_ENV=test`). It routes on a token in the prompt, `[[arc:<name>]]` from the registry in `ai/models/mock/registry.py` (with an optional `[[fault:<name>]]`); a prompt with no token is echoed. Default is the real configured provider. |
| `--email` / `--password` | WDK login override; default to `WDK_DEV_EMAIL` / `WDK_DEV_PASSWORD` (set in `.env.dev`). |
| `--assistant <id>` | which assistant to run. It applies when the thread is new; naming another assistant than an existing thread's is refused. Default: the registry's default. |
| `--quiet` | suppress the live trace; still writes artifacts + prints the summary. |

**Login is mandatory for real runs.** A non-mock `run` logs in to VEuPathDB as the
dev user (creds from `WDK_DEV_EMAIL`/`WDK_DEV_PASSWORD` in `.env.dev`, or
`--email`/`--password`) and runs all WDK calls as that authenticated user. If the
creds are missing or rejected it aborts with a clear error. If the site's
`/login` does not answer it exits with code 2 on one line that names the site
and the failure, such as `cryptodb login did not answer (connect timeout)`, and
the corpus runner records that case as `not-run`. `--mock` skips login
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
| `durable` | running background task | nothing - `--via-worker` waits through the park and captures the completion turn; the gate is left only when the wait timed out |
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
the worker) and record `llm/`.

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
                      # assumed = narrowing values the request did not state
                      #   that the turn's facts part does not carry, over the
                      #   checkpointed spec (the corpus runner's assumed column)
  diagnosis.json      # detected anomalies (see below)
  events.jsonl        # every chunk, raw, untruncated - the SSOT
  tools/NN-<tool>.json# per tool call: phase, FULL args, status, result (the
                      #   summary line a sub-agent step carries), output (the
                      #   whole value: a turn's own call from its
                      #   tool-output-available event, a sub-agent's call from
                      #   llm/*-request.json; null when neither carried it), decoded
                      #   validation errors, duration
  tree.{json,txt}     # turn -> phase -> tool-call span tree
  state/<phase>.json  # ledger + problem-frame snapshot at each phase boundary
  errors/NN-*.txt     # Python tracebacks for any logged exception
  wdk/NN-*.json       # raw WDK request/response (only with --capture-wdk)
  transcript.md       # human-readable trace: calls; the facts part under
                      #   ## Facts, every field it holds, each value with who
                      #   set it as the product shows it (stated, chosen, site
                      #   default, your answer, in the strategy); the reply
                      #   under ## Reply; ## Assumed prints summary.assumed
                      #   (values the facts part does not show) and, apart
                      #   from it, the ledger constraint rows the Lead marked
                      #   source=assumed, which count other things; the step
                      #   a record was read from shows it under that step
  turn_settings.json  # assistant id, phaseModels and phaseReasoning the run sent
                      # ({} means each role at its tier's default)
```

`tools/*.json` is the substrate for surgical debugging: display in stdout is
clipped, but **disk keeps full args and full results** (e.g. the complete
`frame_problem` payload that failed, or `check_study_step`'s `checks[].honored`
under `output`), with Pydantic/`VALIDATION_ERROR`/"unknown
keys" failure strings decoded into a typed `errors[]` list (`kind`, `param`,
`search_name`).

---

## Diagnosis fingerprints (`diagnosis.json`)

The engine (`diagnosis.py`) flags PathFinder's recurring failure modes:

| kind | meaning |
|------|---------|
| `validation_catch_22` | a param is **required by one validator but rejected as unknown by another** - unsatisfiable. This is the `document_type` bug's exact signature. |
| `loop` | one tool failed 5 or more times with no completed call between, completed 5 or more calls whose arguments an earlier call already sent, or met the repetition guard. `summary.loop_detected` reads the same rule (`diagnosis.loops`). |
| `wdk_service_error` | the same search returned a WDK 5xx ≥2 times - the agent retried an unavailable search instead of routing around it. Usually an upstream outage, not a PathFinder bug. |
| `silent_zero` | a step returned 0 results (`ledger.build.zeroResultSteps`) **and the reply never said so** - possible silent failure (e.g. missing JSESSIONID, wrong params). |
| `silent_constraint_violation` | a hard user-explicit constraint was substituted **and the reply never named it** - the plan deviated from what the user asked without saying so. |
| `ungroundable_constraint` | a user-explicit constraint could not be read against the strategy (the ledger's `status: ungroundable` and its `note`): whether the strategy meets it is not known, which is not a violation. |
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
  --sites /app/config/sites/qa.yml --via-worker --only uat-s2-plasmodb \
  --out /data/pf-runs/evals/summary.json
```

`extract` runs one extraction pass by hand; the worker runs it daily on the
`maintenance` queue.

**Run one corpus process at a time.** The cases run against the live sites, and
the client gives each site a few search slots per process; parallel runs in
separate processes each get their own.

**A run is always on the configured provider.** The mock routes by an explicit
marker, so a corpus prompt reaches no arc there; the e2e suite and the unit tier
hold what the pipeline checks. A run needs a VEuPathDB login
(`WDK_DEV_EMAIL`/`WDK_DEV_PASSWORD`), as the chat debugger does.

| flag | effect |
|------|--------|
| `--sites FILE` | required: the sites file every case reads. The recorded counts were measured on the production sites, so a run on `deploy/sites/qa.yml` judges them against QA's builds; the file is named on every run so a run never changes sites silently. With `--via-worker` it must be the file the worker reads |
| `--only NAME ...` | the cases to run; every case when absent |
| `--effort none\|low\|medium\|high` | every role of every case at one effort; wins over the case's `effort` |
| `--via-worker` | every turn through the real worker, so durable tools execute (control tests, sweeps, separations, EDA computes) |
| `--out FILE` | writes `EvalRunSummary` as JSON |

A case can name how it runs, each field compared or applied only when set:

| field | meaning |
|-------|---------|
| `effort` | the effort the case was measured at |
| `gates` | required: `{policy, answers}`. Each answer names the card it answers by its tool and the turn whose message raised it (`{card, turn, accept, comment}` an approval or offer card, `--accept` or `--deny --reason`; `{card: "consult_user", turn, picks}` a question card, `--answer QID=VALUE`, each question taking the options whose label holds a pick, else its recommended ones), and is given once; an answer for a card that never came blocks no later one. `policy` answers every card no answer names: `auto` says yes and takes the recommendations, `stop` does the same but leaves the last turn's card, `decline-offers` says no to an offer, yes to any other approval and leaves a question, `leave` answers nothing. A case that must build nothing may not use a policy that accepts an offer. Every answer goes through `respond` into `turn-N/answer-K` |
| `newConversationBefore` | the turns that open a new conversation for the same researcher, so a memory is read across threads |
| `attachments` | turn index to file names under `evals/corpus/files/`, sent as the composer attaches them |
| `expected.rootCount` | `{count, build, measuredOn}`: the root count a flow recorded, the site build it held on, and the date it was read |
| `expected.countsInGenes` | `true`: what the last turn showed states every count of the strategy's steps in genes, the unit the site counts them in, never as `N transcripts` (`reply_claims.counts_in_the_wrong_unit`) |
| `expected.endsOn` | `none`, `consult`, `approval` or `proposal` (an offer card): the gate the last turn stopped on |
| `expected.unexpressedRequirements` | the rows of the check on the strategy that no search on the site states, counted; `0` holds a withdrawn requirement or a settled question to no gap |
| `expected.turnReplyMentions`, `expected.turnReplyOmits` | turn index to phrases. A mention is read in what that turn showed, its facts part's lines, each value beside who set it as the product shows it, then the reply it ended on after its cards; an omission is read in the reply alone, since the facts part shows a vocabulary term beside its label. `replyMentions` and `replyOmits` read the last turn the same way, and every phrase difference names the text it read |
| `expected.assumedStated` | how many values the run applied that the request did not state and the last facts part did not show with who set them and their measurement (`domain/turn_facts.py::uncarried_assumptions`); compared only when the run counted them, and printed as `assumed=N` (`assumed=-` when uncounted) beside `refusals=` on every case line and in the run's closing line |

**A verdict is `pass`, `re-measure` or `fail`.** The run reads each site's
`buildNumber` once (`services/wdk_build.py`). Any difference but the root count
fails: a changed tree, a missing phrase, a wrong unit, a gate that did not come.
With only the count off, the same build fails, a new build within the larger of
5 genes or 10 % passes, and a new build outside it is a `re-measure` (the exit
criteria's rules for a count that moved). A case whose site login did not
answer is `not-run`: it is no failure and stays out of the pass rate. The
summary counts `reMeasure` and `notRun` beside `passed`, `failed` and `errored`. Each case carries its `observedCount` and, whenever it differs from the recorded count, `countDrift`, which names both counts with their builds, a pass inside the band included.

The `uat-<flow>-<site>` cases are the model-driven UAT flows, written from the
flow tables under `docs/knowledge/uat/`; their provenance names the flow. The
`uat-dry-<tester>-<site>` cases are the dry UAT's investigations, one
conversation each with every message as it was sent (`flows-dry-uat.md`).

---

## `pathfinder.devtools.usage` - cost per conversation, researcher and day

```bash
uv run python -m pathfinder.devtools.usage report [--since 2026-10-01] [--site plasmodb]
```

Reads the `messages` rows of assistant turns (their `metadata.usage.{totalTokens,costUsd}`)
with their conversation and researcher, and prints three tables: per conversation (turns,
tokens, cost, site, assistant, researcher), per researcher, and per UTC day, then the averages
(turns per conversation, cost per conversation, cost per turn). A researcher is named by the
`users.external_id` the sign-in recorded, else by the user id. The cost is what the turn
recorded, so it agrees with the trace cost Langfuse shows for the same turn. Run it where
`DATABASE_URL` reaches the deployment's database (inside the api container, or on the host
with the compose database).

---

## Modules

| file | responsibility |
|------|----------------|
| `chat.py` | CLI: `run`/`respond`/`inspect`/`diff`, bootstrap, turn loop, approval resume |
| `evals.py` | CLI: `staged`/`show`/`promote`/`corpus`/`extract`/`run` |
| `eval_runner.py` | one case per fresh thread, every turn in order, read back from the projection and the checkpoint |
| `capture.py` | `RunCapture` (chunk -> artifacts writer) + `capture_tracebacks` |
| `transcript.py` | the transcript's `## Facts` and `## Assumed` sections |
| `turn_arc.py` | where a worker run stands on the log: running, parked on durable tasks, or ended |
| `models.py` | artifact schema + chunk parsers + validation-error decoder |
| `diagnosis.py` | the fingerprint engine |
| `inspector.py` | `inspect`/`diff` rendering (pure, reads a run-dir) |
| `veupathdb.devtools.wdk_capture` | opt-in WDK httpx capture (`--capture-wdk`) |
| `gates.py` | the gate the CLI detects after a step, and the parts `respond` sends to answer it |
| `usage.py` | CLI: `report` of cost and tokens per conversation, researcher and day |
| `openapi.py` | CLI: `generate`/`check` for `packages/spec/openapi.{json,yaml}` |
| `model_catalog.py` | CLI: `check`/`record`/`probe` for the model catalog against what each provider serves |
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

`model_catalog check` reads the deployment's provider keys from the environment and lists,
per provider, the catalog entries it no longer serves (exit 1), the served ids of a catalog
family the catalog does not hold, and `PRICES_AS_OF`. `record` writes each provider's model
list to `tests/fixtures/provider_models/`, without the models an account trained. `probe
<id>...` sends one request at medium effort, one 1x1 PNG and one one-page PDF, and prints
the two attachment flags it measured. The steps of a refresh are
`docs/knowledge/conventions/refreshing-the-model-catalog.md`.

`RunCapture` implements the `ChatWriter` protocol
(`assistant_core.conversation.event_writer`) - the same surface as the production
`ChatEventWriter`, so the CLI exercises the real turn pipeline.
