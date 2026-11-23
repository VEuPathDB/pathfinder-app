---
type: Decision
title: A message names only its agent's tools
description: Every text an agent receives (instructions, pins, tool descriptions, schemas, tool returns, refusals, capability directives, durable completions, work orders) names only tools that agent holds; the role decides the toolset and the text follows it, a shared text is role-neutral, and a three-layer test holds it. Giving each agent every tool it is told about, a receiver argument on every shared message, attributing text by module path and a hand-kept token list were rejected.
tags: [agents, tools, explore, lead, frame, testing, prompts]
generated: { by: claude-code/opus-5.5, at: 2026-11-23T00:00:00Z }
status: stable
---

# What was decided

**The role decides the toolset, and the text follows the toolset.** A tool is added to an agent
only when its role already calls for that ability and the tool is read-only. Explore gained
`read_experiment` and `get_record_types` this way, and the pinned EDA filter sheet, but not
`ask_eda_cut`. Otherwise the text changes.

**A shared text is neutral.** A sentence two agents receive states the fact or the action and
names no tool. Where one role needs the tool named, that role's own instructions or its own
factory say it: FRAME passes its own WDK next actions (`agents/frame.py::FRAME_NEXT_ACTIONS`) to
`ToolResilience`, whose default names no tool, and `LEAD_INSTRUCTIONS` maps a STALE ledger line to
`get_live_strategy_state`. The client and the tool server name no host tool in a catalog text or
a refusal.

**Three layers hold it.**

- Layer 1 reads every static text from each built agent: its string instructions, its tool
  descriptions and parameter schemas, its output schema and, for FRAME, execution and VERIFY,
  the shared base prompt. A tool whose `prepare` can withhold it (the phyletic builder where the
  OrthoMCL taxonomy is not served, the gene record read where the site has no gene records)
  counts as held here only on the sites that offer it, so a static text never names it; a pin
  that the same site test gates names it instead.
- Layer 2 scans every string literal of `strategist`, `veupathdb`, `veupathdb_mcp` and
  `assistant_core` and keeps those an agent can reach through references from its tools, its
  instruction functions (a pinned section's own render included), its output validators, its
  capabilities and the dispatch texts it is sent. The reach also follows the field types of a
  reached model, the durable body registered for a reached tool declaration, and the graph
  nodes that construct a reached domain model, which is how a node writes state a pin renders.
  It stops at another agent's factory and at a dispatch text another agent receives. A `Field`
  description is a schema text, which layer 1 reads, so layer 2 skips it.
- Layer 3 is an autouse fixture that fails a test when a `FunctionModel` or `TestModel` request
  names a tool the request does not offer. It reads the instructions, the description and schema
  of each offered tool, and the parts new since the last response, a retry included. A refused
  request raises to its caller and the test fails at teardown, so code that catches the error
  cannot hide it. Only a test that builds its own agent or toolset opts out, with the
  `foreign_tool_names` marker and its reason.

**The test checks its own lists against the code.** The agent list equals the `Agent(`
construction sites, the dispatch list equals the texts passed as a work order or a ledger
summary, the scanned packages equal the pinned distributions Strategist imports, every skip glob
matches a file and hides no module an agent reaches, and no retired name is a live tool. An
allowlist entry names its agent, its tool, a substring of its sentence and its reason, and must
match a sentence that exists. In every layer it allows its tool only in a text that holds its
sentence and only for its agent; layer 3 reads the agent from the run's own agent name. Code lives in `tests/_support/tool_names.py`,
`literal_reach.py`, `agent_texts.py` and `boundary_guard.py`.

# What was rejected

- **Giving each agent every tool it is told about.** Explore would then write the strategy, which
  `a-thread-answers-in-explore-or-build.md` forbids.
- **A receiver argument on every shared message.** A neutral sentence serves both receivers with
  less code.
- **Attributing a text by module path.** It read FRAME's work orders as Lead text and missed the
  control-set sentence a sweep refusal sent to Explore.
- **The hand-kept token list of `test_tool_surface_agreement.py`.** It went stale with each new
  tool; layer 1 replaces it.

# What the test cannot see

- Text a remote MCP server returns over the wire at run time (the research server's result
  bodies). Layer 3 sees it only when a test serves a recorded source.
- Error bodies VEuPathDB or EDA return verbatim, which a refusal then quotes.
- Model output relayed between agents: FRAME's result prose to the Lead, the execution agent's
  `actions_taken` and VERIFY's digest. These are generated, not authored.
- A tool referred to without its identifier, such as "the parameter-options tool". Only a review
  sees the meaning.
- Advice that is impossible although every name is held, such as a COLOCATE the structure cannot
  carry.
- A name assembled at run time from variables. Layer 3 sees it only if a test drives that path.
- In layer 2, a method called on a value whose type the reach does not hold: a local variable,
  a parameter, or a model no reached model names as a field. State a node outside
  `strategist.ai.graph` writes, or a node writes into a model outside `strategist.domain`, is not
  followed either.
- Layer 2 counts a site-gated tool as held, because a literal may sit on a path only the sites
  that offer the tool take.
- Layer 3 sees only the paths the suites drive.
