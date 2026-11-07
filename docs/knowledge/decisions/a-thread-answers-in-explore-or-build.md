---
type: Decision
title: A thread answers in Explore or Build
description: Each PathFinder turn runs one of two agents in one graph, Explore or the Lead (Build), chosen by the thread's mode and, in Auto, by one Decisions call on gpt-6-luna with a 0.65 build floor; a resume goes back to the agent that parked, Explore tells the researcher to switch to Build for one buildable reading and offers two or more on a readings card whose pick resumes in Build, while words typed over that card are a new message, and the mode is a row PathFinder owns. A second assistant, a structured Luna router call and a mode column on conversations were rejected.
tags: [modes, explore, router, decisions, lead, graph, persistence]
generated: { by: claude-code/opus-5.5, at: 2026-11-06T00:00:00Z }
status: stable
---

# What was decided

**One graph, two agents.** PathFinder's graph is `route -> lead | explore -> finalize_turn`
(`ai/graph/builder.py`). The route node (`ai/graph/route_node.py::route_turn_node`) picks the
agent, writes the route into the turn state's `mode`, and on a fresh turn emits a
`data-turn-route` part, which the web reads to mark a reply "Explore". On a resumed turn the
Explore node emits the part itself (`ai/graph/explore_node.py`), so every reply Explore wrote
carries the mark. The Lead node and its toolsets are unchanged. The Lead's instructions gain
one line, `LEAD_MODE_LINE`, that names the three modes. `finalize_turn` runs after either
agent. Explore runs no check, so it writes no case memory.

**The thread's mode.** `ChatRequestBody.mode` is `ThreadMode` (`auto`, `explore`, `build`;
default `auto`, `domain/modes.py`). Any other value is refused with 422, the retired `strategy`
included. The dispatcher stores the mode a new message carries in `conversation_modes` (one row
per thread, keyed by conversation id, cascade on delete). It writes nothing on an approval
resume. `ConversationResponse.mode` reads the row back, and a thread with no row reads `auto`.
A branch or a copy opens on the source thread's mode, and a revert keeps it.

**Who answers a turn.** The route node decides in this order:

1. A resume goes to the agent that parked the call (`parked_route`): a completion turn that
   carries the parked durable call's answer, and an answer to the parked card. A typed message
   over a card Explore parked is a new message: it routes by the mode (the router in Auto), and
   the card closes. This holds for the readings card (phase `readings`), a preference to
   remember and a sweep. A typed message over any other card the Lead parked (its own consult
   cards, a FRAME, BUILD or VERIFY card) goes to the Lead, which reads it on its own
   typed-reply path. In the web, typed words over a consult card whose question allows notes
   answer the card as a note. Over a card whose question takes no note, such as the readings
   card, the words are sent as a new message (`takesTypedNotes` in
   `features/conversation/content/parts/consultDraft.ts`).
2. Mode `explore` goes to Explore and mode `build` to the Lead.
3. In Auto, a turn with no words goes to the Lead, and the router decides every other turn.

**The router.** `ai/graph/turn_route.py` asks the OpenAI Decisions API on `gpt-6-luna` one
choice question, `build` or `explore`. The request holds the measured instructions, the last
2,500 characters of `exchanges_text` over the thread's exchanges, the last 1,500 of
`strategy_line` (the step count, the final step's title and its count) and the last 4,000 of
the message. The turn goes to Build only when the build probability is at least
`BUILD_PROBABILITY_FLOOR`, 0.65. A refusal, an error, a key refusal or 5 seconds without an
answer routes to Explore. For a request with one buildable reading, Explore tells the
researcher to switch to Build, and for two or more it offers the readings card. A mock
deployment routes by the `[[arc:<name>]]` token (`ai/models/mock/route.py`): an arc whose name
starts with `explore` goes to Explore.

**Who pays for the router.** The router always runs on the deployment's OpenAI key, also when
the researcher's own key pays for the turn (`decisions_on_the_deployment`,
`platform/model_keys.py::deployment_provider`). Its spend is charged to the turn's usage rows
as paid by the deployment. Before the call, the route node reads the researcher's monthly
deployment allowance (`services/turn_payment.py::spent_deployment_budget`). This has two
consequences:

- When the allowance is spent, every Auto turn goes to Explore with no router call.
- On a deployment with no OpenAI key, every Auto turn goes to Explore.

A researcher who wants Build then picks Build. A database error on that read fails the turn.

**Explore.** `ai/explore/explore_agent.py` runs on `LeadDeps`, so Explore shares the thread's
exchanges, the stated words, the memory store and the site with the Lead. None of its tools
writes the strategy. Its own toolset holds the catalog reads, gene records, the live strategy
state, the gene set listing, the memories, `propose_readings` (counts readings without a step)
and `consult_user`. From the EDA and sweep toolsets it takes only the names in an allowlist
(`_SHARED_TOOLS`): the EDA reads and analyses and the parameter sweep, so a tool added to
either toolset later does not reach Explore. The research tool source (literature and web
search, with no tool that writes) is admitted whole.
`test_explore_holds_no_tool_that_writes_the_strategy` pins the 19 static tool names; the
research source's tools are served at run time and are not in that set. An Explore turn runs
under the Lead's per-turn limits, `lead_usage_limits()` (requests, tool calls and tokens), and
reuses the Lead's stop replies and its model usage part.

**The explore role.** `explore` is a role in every tier and a stage on the Settings picker
("Exploring"). `EXPLORE_MODELS` (`platform/model_catalog.py`) maps each provider and tier to
its explore model: on OpenAI GPT-5.6 Luna for fast and default, GPT-6.1 Terra for balanced,
GPT-6.1 Sol for quality; on Anthropic Haiku 5.5 for fast and default, Sonnet 5.5 for balanced
and quality; on Google Gemini 3.5 Flash-Lite for fast and default, 3.8 Flash for balanced,
Gemini 4 Argon for quality. Every one of them is a model the deployment may pay for, and a
researcher's own key runs the same ones; GPT-6 Astra, Opus 5.5 and Fable 5.1 run Explore only
when a researcher picks one. The effort is the tier's thinker effort. The map is typed by
`KeyableProvider` and `TierName`, and every model is checked against the catalog at import.
There is no fallback for a provider or a tier the map lacks: a new one fails at import until it
gets its line.

A tier a researcher saved before the picker offered Explore holds no explore pick. When every
other pick matches one tier, the web takes that tier's explore model and effort
(`lib/models/tierFill.ts`): the Settings page shows the tier, and the next message stores and
sends the pick (`features/conversation/runtime/turnPicks.ts`). Picks that match no tier, and a
researcher with no picks, are left as they are.

When Explore's model never answers, its stop reply names the Exploring stage
(`fallback_prose(..., own_stage="explore")`); every Build stop reply is unchanged.

**The hand-over.** When the conversation has exactly one reading the site can build
directly, Explore counts it with `propose_readings` and ends its reply by telling the
researcher to switch to Build (or, in Auto, to say "build it"); no card parks. When it has two
or more, Explore counts them with `propose_readings` and ends on `consult_user`. Its validator
(`ai/explore/readings_card.py`) admits only one untyped question whose options are two or
more counted readings, with no note and no replaced requirement. The card parks under the
`readings` phase (`READINGS_PHASE`, `domain/modes.py`), which routes to the Lead, so a pick
resumes in Build, while a typed message over it routes by the mode. When the card parks,
`hand_over_reading` records its labels as one named reading. The Lead's
existing consult path (`ai/lead/lead_consult.py`) then states the pick as a requirement and
Build runs on. Explore writes its exchange and the researcher's words into the shared state,
and never writes `requirements`, `operational_spec` or `original_request`.

# Why

The router was measured on 178 real messages (168 build, 10 explore), 3 runs each, on
2026-11-06. It scored 93.3 percent with identical answers across runs, at 0.14 s median and
about $0.00005 a turn. At the 0.65 floor, 19 of 168 build messages detour through Explore and
9 of 10 explore messages are caught. A detour costs one Explore reply. For a request with
one buildable reading, that reply tells the researcher to switch to Build; for two or more,
it offers the readings card, and a pick builds the reading. A missed concept question costs
a strategy built from words no search states.

The measurement used context text built by hand from recorded runs. Production sends
`exchanges_text` and `strategy_line`, which differ in format on card answers, task results
and the strategy line. The set held only 10 explore messages and no help, remember or
off-topic message. The 0.65 floor stands as measured on 2026-11-06 on those 178 messages with
hand-built context. No re-measure is planned, because no set of explore messages written by
testers exists.

A typed message over the readings card is a new message and not an answer to the card. The
card asks the researcher to pick one counted reading. Words typed instead say something the
card does not offer, so the mode decides who answers them, as for any new message.

A resume skips the router because the parked call belongs to one agent's run. Sent to the
other agent, the answer finds no call to resume.

# Rejected

**A second assistant for Explore.** A thread belongs to one assistant
(`conversations.assistant_id`), so a hand-over would cross threads and lose the checkpoint,
the exchanges and the stated words that Build reads.

**A structured Luna call as the router.** It scored 84.6 and 80.9 percent on the same set, at
about 1 s a turn.

**A mode column on `conversations`.** That table belongs to assistant-core, and the runtime
must not learn one assistant's modes. `conversation_modes` is a PathFinder table, written by
one validated writer.
