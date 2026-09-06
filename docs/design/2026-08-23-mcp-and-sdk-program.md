# The MCP tool protocol and the client SDK: how VEuPathDB teams plug into the assistant runtime (2026-08-23)

> Status: **DESIGN, paper only.** No code was written, changed or run for this document. It is the artifact for the VEuPathDB conversation named in `docs/superpowers/specs/2026-08-22-verification-and-separation-program.md` ("MCP/SDK design track - paper before code"), and it implements workstream WS4 of `docs/assessment/2026-08-17-veupathdb-assistant-platform-assessment.md`.
> Audience: VEuPathDB engineering leadership and the science teams behind the six LLM touchpoints in assessment 1.1.
> Evidence rules used throughout: every claim about VEuPathDB's stack cites the assessment section that measured it; every claim about PathFinder cites a file path in this repository; every claim about MCP cites the **2025-11-25** specification revision by section; every claim about the client library cites the installed source at `apps/api/.venv/lib/python3.14/site-packages/`, read on 2026-08-23.

---

## 0. What this document decides, in one page

**The tool boundary is MCP over streamable HTTP, and the science stays with its owners.** A VEuPathDB team writes an MCP server in Java, Kotlin or R, deploys it their own way, and an assistant on the runtime declares that it wants that server's tools. The runtime resolves the declaration into a live toolset per turn, attaches the right credential, decides which calls need the user's approval, treats every result as untrusted content, and turns declared structured payloads into typed UI parts. Nothing about the science reaches the runtime, and nothing about the credential reaches the assistant.

**Five design calls carry the weight.**

1. **`AssistantSpec` grows exactly one field, conceptually: a list of declared tool sources.** The assistant asks for a named server; the runtime grants a wrapped, credentialed toolset. This is the same split the spec already uses for identity - the assistant declares `identity_gate`, the runtime enforces it (`assistant-platform/packages/assistant-core/src/assistant_core/spec.py:131`, `docs/knowledge/decisions/the-orchestration-is-the-assistants.md`).

2. **Approval is denied by default and granted by annotation, and the annotation is only believed from an admitted server.** A tool runs without a click only when it declares `readOnlyHint: true` and does not declare `destructiveHint: true`. Everything else asks. The mapping is one predicate over `ToolDefinition.metadata["annotations"]`, which is exactly what the library hands us (`pydantic_ai/mcp.py:1160-1164`, `pydantic_ai/toolsets/approval_required.py:29`).

3. **A tool's typed payload is declared once on the tool, not on each result.** The tool names a stream-part kind in its **tool-level** `_meta` and returns the payload in `structuredContent` against its `outputSchema`. It cannot be done on the result, because **pydantic-ai 2.22.0 discards result-level `_meta`** (`pydantic_ai/mcp.py:1579-1594` reads only `structured_content` and `content`; `fastmcp/client/client.py:120-127` shows the `meta` field that is never read). The static form is better anyway: it is checkable at admission and a server cannot invent a new part kind mid-turn.

4. **The user's VEuPathDB token is passed through to a first-party server only, on an allowlist, as a named deviation.** MCP 2025-11-25 says "MCP clients **MUST NOT** send tokens to the MCP server other than ones issued by the MCP server's authorization server" and "MCP servers **MUST NOT** accept or transit any other tokens" (Authorization, Access Token Usage). PathFinder holds the user's registered VEuPathDB token because it acts on WDK **as** the user (`docs/knowledge/decisions/bearer-identity-and-service-tokens.md`), and every WDK-backed feature requires that registered login (`docs/knowledge/decisions/wdk-requires-registered-login.md`). Those two facts collide. The resolution is a per-source credential mode with three values, of which only one carries a user token, and that one is legal only inside VEuPathDB's own trust domain until their authorization server can issue audience-bound tokens per resource. **This is the single most consequential ask in Section 7.**

5. **Every MCP result is untrusted content, including from a first-party server.** Trusting the operator is not the same as trusting the bytes a submitter typed into a record description. The guard runs on tool output, not only on the user's message, and nothing in a result may change approval state after the fact.

**What we build, what they build.** Ours: the declaration and resolution path, the approval predicate, the untrusted-output wrapper, the part-binding convention, `veupathdb-wdk-mcp` over PathFinder's genuinely standalone WDK tools, and the conformance suite as a package a team can run against its own server (**4-6 engineer-weeks**, up from the assessment's WS4 estimate of 2-3, because the conformance suite and the untrusted-output work were priced thin there). Theirs: one reference MCP server on `lib-jaxrs-container-core` that the next five copy (**3-6 engineer-weeks**, unchanged).

**How much less speculative this is than on 2026-08-17.** The assessment's WS4 depended on WS3, which depended on WS2, which depended on WS1. All three have landed (assessment "Status addendum", updated 2026-08-22): the bearer identity path accepts a VEuPathDB token, `application_id` tenancy is enforced through the ownership helpers, the runtime is a package with its own CI lane, `AssistantSpec` exists and two assistants run through one runtime, and the wire protocol is a written, test-pinned document (`assistant-platform/PROTOCOL.md`, version 1.0.0). On 2026-08-17 this program waited on eleven things we had not built. Today it waits on three things we cannot build: their pilot choice, their authorization server's behaviour, and their operational ownership.

---

## 1. Where this sits

### 1.1 What VEuPathDB already decided

MCP is their direction, not ours. Their own roadmap commit reads "realign overall roadmap to local CC+MCP then web-embedded chat+MCP" (`study-wrangler` branch `agentic-wrangling`, 2025-09-18; assessment 0.1). A working stdio MCP server already exists in that branch - `bio-wrangler-mcp`, `@modelcontextprotocol/sdk ^0.5.0` driving R through Rserve, one container per session (assessment 1.1, touchpoint 5). Their two live LLM features are Java on JDK 21 with one-method provider seams (`LlmCompleter`, `JsonPromptClient`), a file-locked daily USD cap that returns HTTP 503, and roughly 100 JUnit tests (assessment 1.1, touchpoints 1 and 2). Nothing in the organisation streams: zero `EventSource`, `text/event-stream` or WebSocket consumers in `web-monorepo`, and every async AI feature is submit-and-poll at about 1 Hz (assessment 1.2, 1.4).

Those four facts set the whole design. MCP because they chose it. Streamable HTTP because their deployment unit is a container behind Traefik, not a subprocess. A conformance suite because a Java team needs a gate it can run itself. A polling client because their frontends have no streaming primitive and their own web-chat plan says the contract should be "agnostic to transport on the front-end side" (assessment 1.2).

### 1.2 What PathFinder already has

- `AssistantSpec` (`assistant-platform/packages/assistant-core/src/assistant_core/spec.py:116-133`) is a frozen model with `assistant_id` and eight declarations: a graph factory, an initial-state factory, an async turn-context factory, a mock-model factory, `checkpoint_types`, a stream-part hook, `memory_kinds`, an identity gate and a turn epilogue. It imports no product module.
- Two assistants run through it: PathFinder (`apps/api/src/pathfinder/assistants/pathfinder_spec.py`) and a pilot (`apps/api/src/pathfinder/assistants/site_help/spec.py`), the latter a single agent with two read-only catalog tools over the bare `TurnState`.
- The `data-*` taxonomy is an open registry on both sides (`assistant-platform/packages/assistant-core/src/assistant_core/conversation/stream_parts/registry.py`), and it already accepts a dotted, namespaced kind: `_schema_name` maps `data-<ns>.<name>` to an identifier by replacing `.` and `-`.
- In-process tools already emit typed parts by returning `ToolReturn(return_value=..., metadata=[DataChunk(...)])` - see `apps/api/src/pathfinder/ai/tools/standalone/workbench.py:87-106` and the chunk builders in `apps/api/src/pathfinder/ai/tools/standalone/_stream_parts.py`.
- Approval already reaches the user: four tools carry `requires_approval=True` (`ai/lead/lead_agent.py:268`, `ai/tools/toolsets/execution.py:112,119`, `ai/tools/toolsets/verification.py:101`), the chunk is `tool-approval-request` (`assistant-platform/PROTOCOL.md` section 5.1), and a sub-agent's approval answer re-enters the sub-agent (`docs/knowledge/decisions/sub-agent-approvals-re-enter-the-sub-agent.md`).
- Identity resolves to one `Principal` in one function: a VEuPathDB ES512 bearer verified against the OAuth server's JWKS, PathFinder's own HS256 bearer, or the session cookie; plus `X-PathFinder-Service-Token` naming the calling application (`docs/knowledge/decisions/bearer-identity-and-service-tokens.md`).

### 1.3 The one library fact that shapes everything

The installed client is **pydantic-ai 2.22.0** with **mcp 1.27.0** and **fastmcp-slim 3.3.1**. `mcp/types.py` sets `LATEST_PROTOCOL_VERSION = "2025-11-25"`, which is the revision this document targets throughout. `MCPToolset` is built on the FastMCP `Client` and accepts a URL, a script path, an in-process `FastMCP` server, a transport or a pre-built client (`pydantic_ai/mcp.py:671-713`). Everything else in Section 2 follows from what that class does and does not carry across the boundary; Appendix A lists the reads.

---

## 2. The tool protocol

### 2.1 How a science team's server plugs into an assistant

**Today, nothing in the platform stops an assistant from using MCP.** `AssistantSpec.build_graph` is a factory that returns a compiled graph, so an assistant may construct its agents with `MCPToolset('https://...')` in `toolsets=[...]` and the runtime cannot tell the difference. That is by design: "the runtime never names a node, an edge, a phase or an agent" (`docs/knowledge/decisions/the-orchestration-is-the-assistants.md`).

**That is not enough, for three reasons that are all the platform's business and none of them the assistant's.**

1. **The credential is the runtime's.** The runtime holds the user's VEuPathDB token; the assistant must never see it, and an assistant that constructs its own HTTP client is holding it.
2. **The approval predicate is a safety property of the deployment**, not a per-assistant preference. If each assistant writes its own, the platform has no answer to "which tools can run without a click here".
3. **Admission is an operator decision.** A server this deployment has not written down must not be reachable, whatever an assistant's code says. MCP's own SSRF section (Security Best Practices) is explicit that client-side URL handling is an attack surface; the mitigation that costs nothing is to accept only operator-configured endpoints.

**So the contract is: the assistant declares, the runtime resolves.**

`AssistantSpec` grows one declaration - conceptually a tuple of **tool source declarations**, each naming:

| Field | Meaning | Owner |
|---|---|---|
| `name` | Local name the assistant uses to ask for the resolved toolset. Also the tool-name prefix, so two servers cannot collide. | assistant |
| `source_id` | The admitted server this refers to. Not a URL. | assistant names it; operator defines it |
| `tools` | Allow-list of tool names, or "everything the server offers". | assistant |
| `required` | Whether a turn may proceed when the server is unreachable. | assistant |

and the deployment's **admission record** - operator configuration, never a request field, never model output - defines each `source_id`:

| Field | Meaning |
|---|---|
| `endpoint` | The streamable-HTTP URL, or a stdio command for a co-located server. |
| `credential_mode` | `none`, `service` or `veupathdb_user`. Section 2.4. |
| `part_namespace` | The single `data-<namespace>.` prefix this server may claim. Section 2.3. |
| `approval_policy` | `annotations` (the default predicate) or `always` (every call asks). Section 2.2. |
| `max_call_seconds` | The per-call budget the runtime enforces. Section 2.6. |
| `content_trust` | `untrusted` always. Present as a field only so it is visible, never so it can be set to anything else. Section 2.5. |
| `conformance` | The passing report and the operator signature that admitted it. Section 4. |

At turn setup the runtime resolves every declaration into a live, wrapped toolset and hands the map to the assistant through the turn-context request, which is already the per-turn seam (`TurnContextFactory` is async precisely so an assistant can read state while building its context; `docs/superpowers/specs/2026-08-22-verification-and-separation-program.md`, batch V1). The assistant's graph factory then decides which agent gets which toolset. The runtime never learns what the tools do; the assistant never learns what credential is attached.

**The wrapping order is fixed and is a platform property**, applied outermost first:

```
ApprovalRequiredToolset(              # asks the user, before any call leaves
  UntrustedOutputToolset(             # scans results, binds declared data parts
    FilteredToolset(                  # the assistant's allow-list
      PrefixedToolset(                # <name>_<tool>, so two servers cannot collide
        MCPToolset(endpoint, auth=...)  # credential attached here, per turn
))))
```

Every one of those wrappers except `UntrustedOutputToolset` already exists in the library (`pydantic_ai/toolsets/`: `approval_required.py`, `filtered.py`, `prefixed.py`, `wrapper.py`). The order matters: approval is decided before the call, so a compromised server cannot talk its way past it, and the untrusted-output wrapper sits inside approval so that nothing it produces can reach the approval decision.

**One consequence to name now.** `MCPToolset` fixes its credential at construction: `auth` and `headers` are `__init__` arguments (`pydantic_ai/mcp.py:848-851`) and `_build_transport` bakes them into the transport (`pydantic_ai/mcp.py:1470-1516`). There is no per-run credential hook. A per-user credential therefore means **a toolset constructed, entered and closed within one turn**. PathFinder's Lead is already built per turn (`ai/agents/registry.py`: "The Lead is built per turn"), but the three sub-agents are module-level singletons with their toolsets baked at import (`ai/agents/frame.py:131`, `ai/agents/execution.py:179`, `ai/agents/verification.py:147`). A sub-agent cannot carry a per-user MCP toolset while it stays a singleton. That is named work in phase P1, not a surprise. The toolset must also be closed: `MCPToolset` is a reference-counted async context manager (`pydantic_ai/mcp.py:1094-1124`), and a session left open leaks a connection per turn.

### 2.2 Annotations map to the approval predicate

MCP's `ToolAnnotations` (mcp 1.27.0, `mcp/types.py`) carries `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint`, all optional, and states its own limitation in the class docstring: "all properties in ToolAnnotations are **hints**. They are not guaranteed to provide a faithful description of tool behavior", and "Clients should never make tool use decisions based on ToolAnnotations received from untrusted servers." The declared defaults matter: `readOnlyHint` defaults false, and `destructiveHint` defaults **true** when `readOnlyHint` is false.

pydantic-ai hands them to us intact. `MCPToolset.get_tools` builds each `ToolDefinition` with `metadata={'meta': mcp_tool.meta, 'annotations': mcp_tool.annotations.model_dump() if mcp_tool.annotations else None, 'task': ...}` (`pydantic_ai/mcp.py:1155-1169`), and `ToolDefinition.metadata` documents exactly that (`pydantic_ai/tools.py:604-608`). `ApprovalRequiredToolset` takes one predicate `(ctx, tool_def, tool_args) -> bool` and raises `ApprovalRequired` when it returns true and the call is not already approved (`pydantic_ai/toolsets/approval_required.py:22-32`).

**The platform predicate, in order:**

1. The assistant listed this tool as always-approve -> **approval required**. An assistant may add friction; it may never remove it.
2. The source's `approval_policy` is `always`, or the source is not admitted -> **approval required**.
3. `readOnlyHint is True` **and** `destructiveHint is not True` -> **no approval**. This is the only path to a silent call.
4. Anything else, including a tool that declares no annotations at all -> **approval required**.

**Why absent means "ask".** A tool with no annotations falls to rule 4, which matches MCP's own default (`destructiveHint` defaults to true) and puts the incentive in the right place: a team that wants its read tools to run without a click writes six characters of JSON, and the conformance suite then holds it to the claim. A platform that guessed "probably safe" would be guessing on the team's behalf about the team's own service.

**Why the hint is trusted at all.** It is not, on its own. The trust comes from admission - a human wrote the source into this deployment's configuration after reading a passing conformance report - and the annotation only distributes that trust across the server's tools. That is why rule 2 exists: an un-admitted server's every call asks, however it annotates itself. The conformance suite (Section 4) makes the claim falsifiable at the level a test can reach; the residual is governance and is stated as governance.

**What the other two hints do.** `openWorldHint` does not touch approval; it raises the scan level for tool output (Section 2.5), because a tool that reaches an open world is the one that can return an attacker's prose. `idempotentHint` does not touch approval either; it decides whether a failed call may be retried without asking again.

**One invariant, stated because it is what makes the whole scheme safe:** approval is decided from the tool definition and the arguments the model produced, **before** the call. Nothing in a tool result can retroactively approve anything, and a `notifications/tools/list_changed` that arrives mid-turn invalidates the cache for the next turn, never the decision already taken.

### 2.3 `_meta` conventions for typed data parts

**The problem.** A Java tool returns a structured payload - say a variable summary or an enrichment table. PathFinder's own tools turn such a payload into a typed `data-*` part that the UI renders as a card rather than as JSON in a code fence. The mechanism is `ToolReturn(return_value=..., metadata=[DataChunk(type="data-gene-set", data=...)])`, which the adapter lifts onto the wire in `iter_metadata_chunks` (`pydantic_ai/ui/vercel_ai/_utils.py:171-188`, which yields only `DataChunk`, `SourceUrlChunk`, `SourceDocumentChunk` and `FileChunk` and drops everything else). An MCP tool returns none of that.

**The constraint found in the library.** The obvious design - put the part declaration in the result's `_meta` - **does not work with the installed client**. `_map_mcp_call_tool_result` reads only `result.structured_content` and `result.content` (`pydantic_ai/mcp.py:1579-1594`); the FastMCP `CallToolResult` carries a `meta` field (`fastmcp/client/client.py:120-127`) that is never read. Per-content-block `_meta` is dropped too, and the source says so in a comment: "Tool results don't preserve MCP annotations/`_meta` ... only `_map_mcp_prompt_part` does that" (`pydantic_ai/mcp.py:1610-1614`). The `process_tool_call` hook does not help, because it wraps `direct_call_tool`, which has already mapped the result (`pydantic_ai/mcp.py:1296-1300`).

**The convention, therefore: declare on the tool, carry in `structuredContent`.**

A tool that wants to render as a typed part MUST declare, in its **tool-level** `_meta` (which does survive, as `ToolDefinition.metadata["meta"]`), a namespaced key:

```json
"_meta": {
  "org.veupathdb.assistant/streamPart": {
    "kind": "data-eda.variable-summary",
    "version": 1
  }
}
```

and MUST declare an `outputSchema` and return the payload in `structuredContent` matching it. `Tool.outputSchema` exists for exactly this in the 2025-11-25 revision ("An optional JSON Schema object defining the structure of the tool's output returned in the structuredContent field"), and `structuredContent` is the one thing pydantic-ai preserves losslessly, unwrapping only the SDK's single-key `result` envelope (`pydantic_ai/mcp.py:1590-1592`).

**What the runtime does with it.**

- At `get_tools()` time it reads the declaration once. The `kind` MUST start with the source's admitted `part_namespace`; a server that claims `data-turn-usage` or another team's namespace is refused at admission, not at call time. Core parts stay bare (`data-turn-status`, `data-task-progress`); product and third-party parts are namespaced. The registry already accepts the dotted form.
- At admission it registers the tool's `outputSchema` as the part's payload schema, so the part flows into the generated OpenAPI index and the open TypeScript union with no hand-written model.
- On each call, the `UntrustedOutputToolset` wrapper returns `ToolReturn(return_value=<the structured payload>, metadata=[DataChunk(type=<kind>, data=<payload>)])`. This works because pydantic-ai unwraps a `ToolReturn` returned from **any** toolset's `call_tool`, not only from a function tool (`pydantic_ai/_tool_execution.py:564-588`).
- If the payload does not validate against the declared schema, the result still reaches the model - it is data, and the model can act on it - but **no data part is emitted** and a conformance violation is recorded. A typed part that was never validated is worse than no part: the UI would render a shape it was promised and did not get.

**Why static declaration is the better design even without the library constraint.** It is checkable before the server is ever called; it does not vary per call, so a renderer can be written once; and a compromised server cannot smuggle a new part kind into a running deployment.

### 2.4 Per-user bearer pass-through, and what a server must never receive

**The collision, stated plainly.**

MCP 2025-11-25 is unambiguous. From the Authorization specification, section "Access Token Usage":

> "MCP servers **MUST** validate that access tokens were issued specifically for them as the intended audience, according to RFC 8707 Section 2."
>
> "MCP clients **MUST NOT** send tokens to the MCP server other than ones issued by the MCP server's authorization server."
>
> "MCP servers **MUST NOT** accept or transit any other tokens."

and, in "Access Token Privilege Restriction": "The MCP server **MUST NOT** pass through the token it received from the MCP client." The Security Best Practices document names the anti-pattern - "Token passthrough" - and closes with "MCP servers **MUST NOT** accept any tokens that were not explicitly issued for the MCP server."

Against that, three PathFinder facts. PathFinder does not answer questions about WDK, it **acts on WDK as the user**, creating strategies and steps the researcher then owns in their own account, which is why `proxied-user-id` was rejected: "A proxied id would let a caller name a user without holding that user's credential, and PathFinder would then have no token to act with" (`docs/knowledge/decisions/bearer-identity-and-service-tokens.md`). Every WDK-backed feature requires a registered VEuPathDB login, and guest minting is deleted (`docs/knowledge/decisions/wdk-requires-registered-login.md`). And VEuPathDB's own client does not validate issuer or audience at all: `OAuthClient.validateClaims` "is an empty method with a TODO", and PathFinder does the same because "a site mints its tokens for its own client id, so a token PathFinder receives from a browser session carries the website's `aud`, not PathFinder's" (same decision).

So the audience machinery the MCP spec relies on does not exist anywhere in VEuPathDB's estate today.

**The design: three credential modes, declared per source, only one of which sees a user token.**

| Mode | What travels | Conformant | When |
|---|---|---|---|
| `none` | Nothing. | yes | Public catalog servers. The default. |
| `service` | A credential the **runtime owns for that server**: a client-credentials token obtained from the server's authorization server with `resource=` naming the server per RFC 8707, or a static secret for a co-located stdio server. | yes | Everything that does not need to act as the user. The server learns which **application** is calling, never which user. |
| `veupathdb_user` | The user's registered VEuPathDB bearer, as `Authorization: Bearer`, on the transport and nowhere else. | **no - a named deviation** | A first-party VEuPathDB service on an operator allowlist that must act as the user on WDK. |

**Why `veupathdb_user` is defensible, and why it is still written down as a deviation.** The receiving server is operated by VEuPathDB, sits inside the same trust domain, validates the token against the same `OAUTH_URL`/JWKS the token came from - the ES512 key at `GET <OAUTH_URL>/jwks`, cached 120 seconds, exactly as `OAuthClient.getValidatedEcdsaSignedToken` does for every container service - and needs that exact credential because WDK will accept no other identity for the user's own steps and strategies. The risks the Security Best Practices document lists are real but bounded here: the audit trail is not lost, because the runtime records the application and the user on its own side and the server sees a token whose `sub` names the same person; the trust boundary is not crossed, because there is one boundary. What is genuinely lost is the ability to revoke PathFinder's access to one server without revoking the user's own session, and the ability to scope down - the user's token is all-or-nothing on WDK.

**The end state, and it is an ask.** VEuPathDB's OAuth server issues audience-bound tokens per MCP server resource (RFC 8707 `resource=`), or supports token exchange (RFC 8693) so the runtime can trade the user's token for one minted for the target server; their services then validate `aud`. At that point every source moves to `service` or to a properly-audienced user token, `veupathdb_user` is deleted, and the deviation closes. Until then, mode 3 is the only thing that lets a science team's server act as the user, and mode 2 is the only thing that is conformant. Section 7 asks them to choose.

**Mechanically**, the credential attaches at `MCPToolset` construction (`auth='<bearer>'` or `headers={'Authorization': ...}`, `pydantic_ai/mcp.py:848-851`), which is why the toolset is per turn (Section 2.1). The runtime attaches it; the assistant's code never holds it and never sees it in `deps`.

**What a server MUST NEVER receive, in any mode.**

- **PathFinder's own HS256 bearer or the `pathfinder-auth` cookie.** Those authenticate to PathFinder's API. A server holding one is the user, inside PathFinder.
- **`X-PathFinder-Service-Token`.** It names the calling application against `PATHFINDER_SERVICE_TOKENS`; a holder can impersonate the application.
- **`VEUPATHDB_AUTH_TOKEN`, the service account.** It is confined to user-independent reads by a transport guard that refuses a `/users/<id>/...` call carrying no request token (`docs/knowledge/decisions/wdk-requires-registered-login.md`). Handing it out defeats the guard.
- **Any credential in a tool argument, in `_meta`, or in a URL query string.** Credentials travel in the transport's `Authorization` header and nowhere else. The MCP spec is explicit: "Access tokens **MUST NOT** be included in the URI query string."
- **A guest token.** There are none. VEuPathDB refuses guest and anonymous WDK service calls, measured on plasmodb.org and toxodb.org, and guest minting is deleted from the product.
- **Another source's credential.** One toolset, one credential, one source. There is no shared client.

**And one thing the runtime must never do:** follow an OAuth discovery URL a server supplies into a private address range. Because every endpoint and every credential here is operator configuration rather than server-discovered, the SSRF surface the MCP Security Best Practices document describes is mostly closed by construction. Say so in the admission record rather than relying on it silently.

### 2.5 Tool output is untrusted content

The assessment's gap 7 is still open: untrusted web content enters the context unscanned (`ai/tools/standalone/research.py` via the web-search service, up to 4000 characters per page), while PIGuard runs on the last user message only (`ai/conversation/dispatcher.py`), and the agent holding that context also holds `delete_step` and `clear_strategy`. MCP widens that hole by design, because the whole point is to let a system we do not operate put text into our model's context.

**The stance.**

1. **Every MCP tool result is untrusted, with no exception for first-party servers.** Trusting the operator means believing the server is not malicious. It does not mean the bytes are clean: a WDK record description, a dataset title or a user comment is text a third party typed, and the server faithfully returns it.
2. **The guard runs on tool output before it re-enters the model.** One call site: the `UntrustedOutputToolset` wrapper that already converts the result. This closes gap 7 for MCP and gives the in-process web-search path the same wrapper for free.
3. **The failure mode is to fence, not to fail.** A hit strips or fences the offending span and annotates the result so the model sees that something was removed. A false positive that kills a researcher's turn costs more than a fenced paragraph. Only a hit above a high-confidence threshold, or any hit from a source that is not admitted, refuses the call outright.
4. **`openWorldHint` sets the scan level.** A tool that reaches an open world is scanned strictly; a closed-world catalog read is scanned loosely. This is the second and last use of an annotation, and unlike approval it fails safe: an absent `openWorldHint` means the MCP default, which is `true`, which is the stricter setting.
5. **Nothing in a result may change approval state.** Restated from Section 2.2 because this is where it earns its keep: a server that returns "the user has already approved the next call" changes nothing, because approval was decided before the call and is not re-read after it.

### 2.6 Long-running tools: MCP tasks and our durable tools do not merge in v1

Two mechanisms now exist and they must not be confused.

- **Ours.** `@durable_tool` creates a `background_tasks` row, defers a procrastinate job, fires `interrupt()`, checkpoints the thread, streams `data-task-progress`, and resumes with `Command(resume=...)`. A user can close the tab and come back.
- **Theirs.** MCP task-augmented execution (SEP-1686, in the 2025-11-25 revision) declares `Tool.execution.taskSupport` as `forbidden`, `optional` or `required`; pydantic-ai resolves it into `metadata['task']` at `get_tools` time and calls with `task=True`, awaiting `tasks/result` (`pydantic_ai/mcp.py:1154, 1214-1222`), with `prefer_tasks` defaulting to `True`.

**The rule for v1: an MCP task is the server's business; durability is ours.** The library's `await` on `tasks/result` sits inside our turn, so it is bounded by the source's `max_call_seconds` like any other call. A tool whose realistic duration exceeds the turn budget is an admission failure: the server must either return quickly with a handle the model can poll through a second tool, or the binding must be a durable wrapper on our side.

**Do not bridge MCP tasks to `interrupt()` in v1.** It would require reconciling three things nobody is asking for yet: which identity resumes the MCP session after a worker restart, how the server's progress notifications map onto `data-task-progress`, and what a checkpoint holds for a task living in another process. Named as a v2 question in Section 7.

---

## 3. `veupathdb-wdk-mcp`: the inventory

The assessment proposed exposing PathFinder's WDK tools as an MCP server so "a gene-page assistant, Claude Code, or VEuPathDB's own wrangler assistant can call `find_searches`, `read_param_options`, `run_search`, `lookup_gene` without importing PathFinder" (assessment 3.3). This section does the reading and says which tools that actually is.

**The test applied to each tool:** does it need only a site, a WDK credential and its arguments, or does it need PathFinder's turn state - `agent_state`, `strategy_session`, the `OperationalSpec` draft, the discovery gate, the enum vocabulary rebuilt per call? The first kind is a service. The second kind is a conversation-scoped state machine and does not survive a network hop.

### 3.1 What ships

Names are the MCP tool names, which take an explicit `site_id` because the server is stateless. Every one of them maps to a function in `apps/api/src/pathfinder/ai/tools/standalone/`.

| MCP tool | Source | `readOnlyHint` | `destructiveHint` | `openWorldHint` | Credential |
|---|---|---|---|---|---|
| `list_record_types` | `catalog.py:26` `get_record_types` | true | - | false | service |
| `search_for_searches` | `catalog.py:41` (retrieval half only) | true | - | false | service |
| `browse_search_categories` | `catalog.py:106` | true | - | false | service |
| `list_searches` | `catalog.py:126` (retrieval half only) | true | - | false | service |
| `list_transforms` | `catalog.py:147` | true | - | false | service |
| `lookup_phyletic_codes` | `catalog.py:163` | true | - | false | service |
| `search_example_plans` | `catalog.py:184` | true | - | false | service |
| `get_search_overview` | `catalog_discovery.py:92` (WDK read + formatting only) | true | - | false | service |
| `get_parameter_options` | `catalog_discovery.py:164` (vocabulary read only) | true | - | false | service |
| `lookup_gene_records` | `gene.py:16` | true | - | false | user |
| `resolve_gene_ids_to_records` | `gene.py:45` | true | - | false | user |
| `get_step_estimated_size` | `execution.py:16` | true | - | false | **user** |
| `get_step_sample_records` | `results.py:69` (with `record_type` as an argument) | true | - | false | **user** |
| `get_step_download_url` | `results.py:26` | true | - | false | **user** |
| `run_control_tests_on_search` | `experiment.py:96` | **false** | **false** | false | **user** |
| `enrich_gene_ids` | new, over `services/gene_sets` + enrichment | **false** | **false** | false | **user** |

Sixteen tools in four groups: catalog (9), records (2), step reads (3), evidence (2). That is a real server for a gene-page assistant, for Claude Code and for the wrangler.

**Notes that matter for the annotations and the auth column.**

- **The catalog group is user-independent** and may run on the service account: record types, searches, parameter metadata and vocabularies are exactly the reads `docs/knowledge/decisions/wdk-requires-registered-login.md` permits it. That is what makes a gene-page assistant possible for a visitor who is not signed in - **if** such a credential exists for a host other than PathFinder, which is Section 7's first ask.
- **The three step reads name a user's own step**, so they hit `/users/...` and the transport guard refuses them without a request token. `user`, always.
- **`run_control_tests_on_search` is the most interesting export and the only one that writes.** It creates a temporary WDK strategy to intersect a search's results with control gene IDs (`experiment.py:96-135`). It is `readOnlyHint: false` and `destructiveHint: false` - additive, it creates and does not remove - which under the Section 2.2 predicate means it asks for approval on every call. That is the correct answer: it writes into the researcher's own VEuPathDB account.
- **`lookup_gene_records` and `resolve_gene_ids_to_records` are marked `user` conservatively.** The site-search path may well work on the service credential, but `resolve_gene_ids_to_records` runs a search over `GeneByLocusTag` and the guard's rule is about the path, not the intent. The conformance suite measures it rather than this document asserting it.
- **`enrich_gene_ids` is a new tool, not an export.** `run_gene_set_enrichment` (`workbench.py:149`) takes a `gene_set_id` into PathFinder's own store, which no other consumer has. The MCP tool must take the genes by value plus a background source. Its result shape is a conformance case in its own right, because the field names are load-bearing and wrong ones yield an empty column rather than an error: GO uses `goId`/`goTerm`, Pathway uses `pathwayId`/`pathwayName`, and Word uses `word` plus **`pathwayName`** (rule WDK-ANS-007, `docs/knowledge/wdk/rules/searches-and-answers.md`).
- **Four tools are split, not moved.** `search_for_searches`, `list_searches`, `get_search_overview` and `get_parameter_options` each do a WDK read and then write PathFinder's discovery gate: `search_for_searches` calls `ctx.deps.agent_state.record_catalog_searches(...)` and hides already-decided searches (`catalog.py:83-101`); `get_search_overview` returns an `AlreadyReadNotice` on a second read, calls `register_search(deps.agent_state, ...)`, and passes `deps.agent_state.operational_spec_draft.goal` into the formatter (`catalog_discovery.py:109-143`); `get_parameter_options` keeps a read-dedup ledger keyed on the exact context and query (`catalog_discovery.py:206-215`). **The retrieval is the service; the gate is PathFinder's.** PathFinder keeps a thin local wrapper that calls the MCP tool and then records. This is the general pattern for every future export, and it is the reason the split is worth doing rather than exporting the tools as they stand.

### 3.2 What stays PathFinder-internal, and why

**The FRAME binding tools are the definition of orchestration-coupled.** `set_criterion`, `set_structure` and `drop_criterion` (`frame_spec.py:474, 626, 654`) write the `OperationalSpec` draft on `agent_state`; they raise `ModelRetry` against a parameter sheet the agent read earlier in the same turn (`_refuse_unknown_names`, `_refuse_undecided`, `_refuse_unmatched_value`); they reconcile dependent parameters against the spec's prior bindings (`_reconcile_dependents`, `_phyletic_overrides`, `_radio_overrides`); and their enum vocabulary is rebuilt on every call from `candidate_search_names()` union `discovered_search_names()`, minus whatever the service-outage tracker has withdrawn this turn (`ai/tools/toolsets/frame.py:35-49`). None of that is expressible as a stateless call. Exporting them would mean exporting the turn.

The rest, with the reason in one clause each:

- **Strategy mutation** - `build_strategy`, `apply_operations`, `update_leaf_params`, `update_combine_operator`, `update_step_metadata`, `delete_step`, `replace_subtree`, `insert_saved_strategy`, `add_step_filter` / `add_step_analysis` / `add_step_report`, `rename_strategy`, `clear_strategy`: they mutate the turn's `StrategySession` graph and are enum-guarded on live step ids.
- **`get_strategy`, `request_search_inspection`, `think`**: they read or steer the turn itself.
- **`search_memory` and `remember`**: the memory store is the runtime's, namespaced `("app", application_id, "user", user_id, kind)`. Exposing it over MCP would let a server read another assistant's user memories. Never.
- **Workbench gene sets and experiment reads** - `create_workbench_gene_set`, `list_workbench_gene_sets`, `export_gene_set`, and the seven `workbench_read.py` getters: they key on PathFinder's own store and the turn's experiment.
- **The durable pair** - `run_control_tests_on_step` (`experiment.py:64`, about 3 minutes) and `optimize_search_parameters` (`optimization.py:31`, about 15 minutes): they name a built step in our session and resume through our checkpoint.
- **The comparison and control-set tools** on the Lead's own list - `compare_search_variants`, `compare_variants_scored`, `build_control_set`, `list_control_sets`, `import_control_ids_from_gene_set`, `import_control_ids_from_strategy`, `consult_user` (`ai/lead/lead_agent.py:254-269`): they are the orchestration.
- **`web_search` and `literature_search`**: standalone in shape, but they spend our provider keys against our budget. Exposing them makes PathFinder a paid proxy for anyone who can reach the server. A separate decision, not this one.

---

## 4. The conformance suite

A server is admitted when a human has read a passing conformance report and written the source into this deployment's configuration. The report is what the suite produces.

### 4.1 The six families

**1. Shape.** `initialize` negotiates a protocol revision the runtime supports; name it in the report (this program targets `2025-11-25`, the `LATEST_PROTOCOL_VERSION` of the pinned `mcp` 1.27.0). `tools/list` returns tools with unique, prefix-safe names and a non-empty `description`. Every `inputSchema` is an object schema the runtime's validator accepts, because pydantic-ai validates arguments against it before the call. A tool that declares `org.veupathdb.assistant/streamPart` in its `_meta` MUST also declare an `outputSchema` and MUST return `structuredContent` that validates against it.

**2. Auth.** With no credential, every tool call fails as a protocol error, never as a result. With a wrong or expired credential, the same. An unauthorized request answers `401` with a `WWW-Authenticate` header carrying `resource_metadata`, which MCP 2025-11-25 requires of HTTP-transport servers ("MCP servers **MUST** implement the OAuth 2.0 Protected Resource Metadata specification"), and which **no VEuPathDB service publishes today** - so this is genuinely new work, not a checkbox. No credential appears in any result, error message or log line. And the case the assessment says we lacked and the tenancy work then proved we needed: **two-user isolation** - user A's credential cannot read user B's step, over every tool that names one.

**3. Annotations.** Every tool declares `readOnlyHint` explicitly; absent is a failure, because absent means "approve every call" and a team should choose that knowingly. A tool declaring `readOnlyHint: true` is called twice with the same arguments against a fixture account and the account is compared before and after: nothing new appears. A tool declaring `destructiveHint: false` is called against a fixture and nothing that existed before disappears. `idempotentHint: true` is called twice and the results compared. These are the falsifiable parts; the rest is the operator's signature on the admission record, and the report says so rather than pretending otherwise.

**4. Errors.** A failing tool returns `isError: true` with content a model can act on, not a stack trace and not an HTTP 500. A bad argument is a tool error, not a transport error. This one has a measurable cost attached: the runtime's default is `tool_error_behavior='retry'`, which converts a tool error into a `ModelRetry` (`pydantic_ai/mcp.py:1562-1576`), so an error that does not name the offending field buys a wasted model turn. The suite asserts the message names it.

**5. Timeouts and cancellation.** The server answers `initialize` within the client's `init_timeout` (5 seconds by default, `pydantic_ai/mcp.py:955-956`). Every tool returns within the source's declared `max_call_seconds`, or declares `execution.taskSupport` and returns a task. The suite drives a call past the budget and asserts the runtime's timeout fires **and the turn survives**. A cancelled call leaves no half-written object in the fixture account.

**6. Stability.** `tools/list` is identical across two fresh connections. A change emits `notifications/tools/list_changed`, which is what invalidates the client's cache (`pydantic_ai/mcp.py:1450-1467`); a server that changes its tool set silently leaves every client stale and fails admission.

### 4.2 Who runs it, and when

- **The team, first, on its own CI.** The suite ships as a runnable package - a pytest plugin plus a container that hosts the fixture account - so a Java team runs it against its own server on every pull request, long before it asks for admission. This is the same two-lane shape the science layer already uses (`docs/superpowers/specs/2026-08-22-verification-and-separation-program.md`, batch V3): a hermetic lane against recorded fixtures for speed, and a live lane against the real server for truth.
- **The operator, at admission.** A passing report plus a signature is what writes the source into the deployment. There is no self-registration and no discovery: a server nobody wrote down does not exist.
- **The deployment, nightly.** Every admitted source is re-run against the live server, like the WDK live lane. A failure alerts and quarantines the source; it does not block a PathFinder pull request. That mirrors the promotion policy already ruled for evals: a check becomes a hard gate only after it catches a real regression and holds stable, and a flaking gate is demoted, never suppressed.

---

## 5. The reference Java server

### 5.1 Transport: streamable HTTP, not stdio

Four reasons, in decreasing order of how hard they are to argue with.

1. **stdio requires the client to spawn the server as a child process**, which means the server ships inside the runtime's container. That is impossible when the science is theirs and the runtime is ours, and it is the one shape the MCP Security Best Practices document singles out for sandboxing, one-click consent dialogs and command-pattern warnings ("Local MCP Server Compromise").
2. **Their deployment idiom is already an HTTP service.** `alpine-dev-base:jdk-21-gradle-8.7` -> `shadowJar` -> `amazoncorretto`, a 12-line Jenkinsfile via `pipelib`, per-stack docker-compose, Traefik ingress, Watchtower auto-update, Puppet-managed hosts, no Kubernetes (assessment 1.3). An HTTP server drops into that with a route and a health check. A subprocess does not drop into it at all.
3. **MCP authorization is defined for HTTP transports only.** The specification says implementations using stdio "**SHOULD NOT** follow this specification, and instead retrieve credentials from the environment" - which is precisely the wrong shape for a per-user credential.
4. **SSE is deprecated in the Java SDK's 2.0 line** in favour of streamable HTTP, so picking SSE would be picking a deprecated transport on day one.

The existing `bio-wrangler-mcp` prototype is stdio on `@modelcontextprotocol/sdk ^0.5.0` (assessment 1.1, touchpoint 5); moving it to streamable HTTP is the upgrade the assessment's WS4 already priced at part of their 3-6 EW.

### 5.2 The Java SDK, as of this reading

Read on 2026-08-23 from the SDK's repository and documentation:

- Group `io.modelcontextprotocol.sdk`. Latest release **2.0.1**; the major is **2.0.0**. It targets MCP specification revision **2025-11-25**, the same revision this document targets and the same one the pinned Python client implements.
- **Java 17+**, so their JDK 21 baseline is comfortably inside it.
- Modules: `mcp-bom` (version management), `mcp-core` (the primary implementation: STDIO, a JDK `HttpClient`-based client, and a **Jakarta Servlet** server transport), `mcp-json-jackson2` and `mcp-json-jackson3`, `mcp` (core plus Jackson 3), `mcp-test`.
- **Spring WebFlux and WebMVC transports moved out** of the SDK into Spring AI 2.0+, so a non-Spring service is a first-class citizen rather than an afterthought.
- **SSE transports are deprecated in favour of streamable HTTP** as of 2.0.0.
- The SDK is validated against the MCP conformance test suite (version 0.1.15 at this reading), which is a useful precedent for Section 4: the ecosystem already expects a server to pass a suite.

**The one technical unknown, stated as an unknown.** `mcp-core`'s server transport is Jakarta Servlet-based, and `lib-jaxrs-container-core` runs JAX-RS. Whether the Servlet transport mounts inside their container or whether the service runs the SDK's own HTTP server behind the same Traefik route is a half-day spike, and I could not settle it by reading from here. It is the first thing to try, and it is the reason the estimate below starts with a spike rather than with tools.

### 5.3 What the 3-6 EW buys, decomposed

| Slice | Size | What is in it |
|---|---|---|
| Skeleton and transport spike | 0.5-1 EW | A `lib-jaxrs-container-core` service; the Servlet-vs-standalone decision; Jenkinsfile, compose entry, Traefik route, health endpoint, Prometheus. All of it their existing idiom. |
| Authorization | 0.5-1 EW | Bearer validation reusing `OAuthClient`; **RFC 9728 protected-resource metadata** and the `WWW-Authenticate` challenge on 401. This is the genuinely new part - no VEuPathDB service publishes protected-resource metadata today. |
| Tools | 1-2 EW | Three to five real tools with `inputSchema`, `outputSchema`, annotations, the `_meta` stream-part declaration, and the error contract. |
| Conformance | 0.5-1 EW | The suite green, including the two-user isolation case and the timeout case. |
| Handover | 0.5-1 EW | Documentation written so the next team copies rather than asks. |

**What they get is a template, not a service.** The point of the reference server is that the second one costs about 1 EW and the fifth costs a day. If the first server is written as a one-off, the program does not scale and the whole argument for MCP over "each team builds its own assistant" collapses.

---

## 6. The SDK story: the client side

### 6.1 The protocol document is the contract

`assistant-platform/PROTOCOL.md` is version 1.0.0 and it is a real specification, not a summary: RFC 2119 keywords, a framing grammar, cursor semantics, the chunk vocabulary, the turn shape, and a reducer written as five rules. Every example in it is captured from a real turn by `tests/integration/conversation/test_protocol_document.py`, which fails when the runtime and the page disagree. Its versioning rule is the same one the runtime package uses: additive within a minor version, and removing or retyping anything is a major version with every registered assistant migrated in the same change.

That is what a Java or R consumer builds against. It exists today.

### 6.2 `assistant-platform/packages/assistant-client-ts`

The TypeScript headless client is batch V5 of the verification and separation program, being built in a parallel batch, and this document deliberately does not depend on its internals. Its role, from that spec: it is the client for hosts that write their own UI in their own stack, and **its tests double as protocol conformance from the consumer side** - which is the property that matters here. A protocol with one implementation on each side is a pair of programs that agree; a protocol with a specification, a producer test and an independent consumer test is a contract.

For `web-monorepo` this is the second of the three embedding options the assessment ranked, and the recommended one after the iframe: peer dependencies are fine but the host's TypeScript 4.9 and Tailwind-4-inside-MUI-4 CSS isolation make a shipped React component multi-week and low-value (assessment 2.2). A headless client sidesteps both, and it matches what their AI features already do - the AI-comments feature deliberately used local React state and needed no Redux module (assessment 1.4).

### 6.3 The polling fallback is the adoption path

Their frontends have no streaming primitive at all - zero `EventSource`, `text/event-stream` or WebSocket consumers anywhere in `web-monorepo` - and their own web-chat design says the contract should be "agnostic to transport on the front-end side" (assessment 1.2, 1.4). Every async AI feature they run polls at about 1 Hz.

PROTOCOL.md already licenses exactly that, in section 4: "A client that cannot hold a long-lived connection MAY poll the snapshot instead; the ordering and the bytes are identical either way." The durable event log is what makes it true - every chunk is a row with a monotonic cursor, so a tail and a poll return the same bytes in the same order.

**So a minimal Java or R client is four things**, and none of them is an SSE parser:

1. An HTTP client that can POST a turn and GET a snapshot.
2. A JSON parser.
3. The reducer in PROTOCOL.md section 9 - five rules, roughly sixty lines in any language.
4. A cursor it persists per thread.

That is the offer to make in the meeting: **you do not need to adopt streaming to adopt the assistant.** Offer both; do not make SSE a precondition (assessment risk 2).

### 6.4 Two gaps a non-JS consumer will hit, and they are ours to close

Being honest about what the document does not yet say:

- **The request side is unspecified.** PROTOCOL.md sections 2 through 9 specify what a client *reads*. The POST body that starts a turn - `{conversationId, siteId, id, trigger, messages[], phaseModels?, phaseReasoning?, assistantId?}` - is described in the assessment (2.2) and in the code, not in the protocol document. A Java consumer cannot start a turn from the page alone.
- **Durable-task progress is a second, incompatible SSE dialect.** `GET /api/v1/conversations/{id}/tasks/{task_id}/events` speaks its own shape rather than the v6 chunk vocabulary (assessment 2.2, finding 6). A consumer that renders a long-running tool has to implement two protocols.

Both are **additive** changes to PROTOCOL.md - a new section for the request side, and unifying the task dialect onto the existing `data-task-progress` part which is already in the vocabulary. Both are prerequisites for a non-JS consumer, and both should land as version 1.1 before the first external client is written rather than after.

> **Closed, 2026-08-23.** Both landed as PROTOCOL.md 1.1.0, after this document was written. The request side is section 12, with the field split, the resume, the refusals and two captured examples. The durable-task lifecycle is on the thread, in the section 6 subsection that names it, coalesced; the per-task endpoint keeps working and is specified as a deprecated legacy channel in section 13. The paragraphs above are left as written, because they are the analysis that produced the work.

---

## 7. The asks

Assessment Section 7 listed the decisions only VEuPathDB can make. Here they are as concrete meeting items, each with the default we propose so that silence still produces a decision.

**Ask 1 (first, because it gates the pilot). Is there a read-only service credential for a host other than PathFinder?**
The status addendum leaves this open: "whether a service-account API key exists that would let a host offer read-only exploration without a per-user login". For a gene-page assistant it is the whole question - a visitor reading a gene page is not signed in. If the answer is yes, the catalog half of `veupathdb-wdk-mcp` serves everyone and the pilot has an audience. If no, the pilot answers only for signed-in users and we should know that before we build it.
*Our default if unanswered:* build for signed-in users, and treat anonymous read as a later enhancement.

**Ask 2. Which application first? We argue for the gene-page assistant.**
Four reasons, and one rejection.
1. Its neighbours are already live and already on a record page: `AiExpressionSummary` mounts through a `RecordAttributeSection` override and the AI-comments UI sits under `userComments/AiGenePublication` (assessment 1.1, 1.4). The mounting pattern is proven and is a one-file change.
2. Its entire tool surface is the read-only half of `veupathdb-wdk-mcp` (Section 3.1). The pilot and the MCP server are the same work, not two.
3. It needs no strategy state, so it fits the shape that already runs: one agent over the bare `TurnState`, exactly like `apps/api/src/pathfinder/assistants/site_help/spec.py`.
4. The hardest product question - what is the user talking about - is answered by the URL.
*Rejected as first, not as wrong:* the VDI upload wrangler. `bio-wrangler-mcp` exists, which is genuinely attractive, but its tools mutate a researcher's upload, it needs R container orchestration per session, and it has the hardest consent surface in the estate. It is the right **second**.

**Ask 3. Auth: does `auth.veupathdb.org` support RFC 8707 `resource`, and will `validateClaims` ever validate `aud`?**
This decides whether a science team's MCP server can act as the user. Three sub-questions, in order: (a) can the authorization server mint a token audienced to a named MCP resource; (b) is token exchange (RFC 8693) available so the runtime can trade the user's token for one minted for the target; (c) if neither, will you sign off in writing on the first-party passthrough allowlist described in Section 2.4?
*Our default:* `service` mode everywhere it works, `veupathdb_user` only on an allowlist, reviewed at each admission, and the deviation recorded as a decision in this repository rather than left implicit.

**Ask 4. Deployment: the MCP servers are yours, deployed your way.**
*Our default:* compose plus Jenkins plus Traefik plus Watchtower plus Puppet, with the conformance suite as the gate and no Kubernetes assumed anywhere. The runtime is one more container in the same idiom. What we need from you is who operates Postgres with pgvector, which image registry, and how secrets reach a container (conifer, or environment).

**Ask 5. Budgets, and the consent hook.**
Per-application budgets are the open row in the assessment's hardening table. *Our default:* a per-application daily cap plus a global deployment cap that return **HTTP 503**, because that is the pattern your `DailyCostMonitor` already uses and the pattern your UI already degrades against gracefully (assessment 1.1, 1.2). MCP calls are attributed to the application that made them, and a source that exceeds its budget is quarantined rather than silently slowed.
On telemetry: the consent switch already exists - `users.eval_data_consent`, read and written through `GET`/`PATCH /api/v1/me/privacy`, default on, with a one-screen notice and an inline opt-out (`docs/knowledge/decisions/a-staged-eval-case-carries-its-user-until-promotion.md`). *Our default:* MCP tool arguments and results ride that same flag rather than growing a second one, staged and redacted the same way, with the same check constraint that makes a promoted case unable to name anybody. The question for you is whether that is sufficient for tool traffic that crosses into your services, or whether an MCP call needs its own consent.

**Ask 6. Data policy for tool traffic specifically.** Retention of MCP request and response bodies, whether a server may log arguments, and what "delete my account" must reach on your side. PathFinder's purge is per application today and there is no first-party "erase everything across applications" action yet.

**Ask 7. The private repositories, restated with a new reason.** Names and read access for the chatbot work, and whether `PubLLicanProject` and `agentic-wrangling` are in scope. The new reason: every one of them is a potential MCP **client**, and a conformance suite written against two consumers is worth several times one written against ours alone.

**Ask 8 (new, small). Do you want MCP task-augmented execution bridged to our durable tasks?**
Section 2.6 says no for v1 and gives the three things that would have to be reconciled. If one of your tools genuinely runs for fifteen minutes and must survive a client disconnect, say so now and it changes the phasing.

---

## 8. Phasing

> **Executed, 2026-08-25.** The in-repo half of this program ran as
> `docs/design/2026-08-24-mcp-sdk-execution-plan.md`, batches A through G;
> what each batch landed is in `docs/knowledge/log.md` under 2026-08-24 and
> 2026-08-25. P1's exit criteria are met and each is named by a test:
> `assistant-platform/packages/assistant-core/src/assistant_core/mcp/` holds the declarations,
> the admission record, the approval predicate, the untrusted-output wrapper
> and the per-turn resolution. P2 serves the sixteen tools of section 3.1 from
> a container of their own and ships `assistant-platform/packages/mcp-conformance`, which answers
> `incomplete` against our own endpoint with its six unsettled checks pinned
> by name rather than skipped. P4's in-repo half is proven: `site_help`
> answers a turn whose tools this deployment served over the network,
> approval included. P3 and P5 are VEuPathDB's, and section 7's asks are
> unanswered, so the table below stands as written. One correction the work
> found: the P1 prerequisite named at the end of 8.2 had already closed before
> this program started - the runtime owns the deferred-tool cycle in
> `assistant_core/graph/approvals.py`, PROTOCOL.md 1.2.0 records it, and the
> backlog file that paragraph cites no longer exists.

### 8.1 How much less speculative this is than on 2026-08-17

The assessment put WS4 behind WS3, behind WS2, behind WS1. All three prerequisites landed, and the status addendum records each with its evidence:

- **WS1, partly.** A VEuPathDB bearer token authenticates directly, verified as an ES512 JWT against the JWKS, mapping to the internal user through the same WDK resolver the refresh route uses; `X-PathFinder-Service-Token` names the calling application; OpenAPI declares `HTTPBearer` and `APIKeyHeader`; CSRF is required of cookie requests only. `application_id` tenancy is enforced inside the ownership helpers over six tables, with an authorization matrix that proved it over every mutating route and found 21 leaking before. Worker concurrency, model validation and telemetry redaction are closed.
- **WS2.** Both hard entanglements are gone; the `data-*` taxonomy is an open registry on both sides; import-linter contract 7 states that the assistant runtime never imports the science, directly or indirectly.
- **WS3-0/1/2.** `AssistantSpec` exists and imports no product module; `pathfinder/assistants/` is the composition root; `conversations.assistant_id` routes; a second assistant runs.
- **V1.** The runtime is a package with its own pyproject, lock, test tree and CI lane, and it cannot import `pathfinder` at all.
- **V2.** A synthetic assistant built from runtime code alone drives turns, durability, resume, cancellation, cost and tenancy with no product present, and **PROTOCOL.md 1.0.0 exists and is test-pinned**.
- **V3, V4.** Science verification runs in two lanes with 78 of 79 WDK rules enforced and 139 live tests; the eval system has consent, extraction, staging, curation and first cases.

So: on 2026-08-17, WS4 was a plan resting on eleven unbuilt things. Today it rests on three things we cannot build - your pilot choice, your authorization server's behaviour, and who operates what.

### 8.2 The phases

| Phase | Who | Size | Exit criterion |
|---|---|---|---|
| **P0. This document and the meeting** | joint | 0 (done) | The pilot is named; Ask 1 and Ask 3 are answered; the passthrough allowlist is signed or refused. |
| **P1. The tool protocol, proven in-process** | ours | 1-1.5 EW | Against an in-process FastMCP server in tests, with no network and no VEuPathDB dependency: a tool served over MCP appears in a real turn; a `destructiveHint` tool asks for approval and a `readOnlyHint` tool does not; a declared `structuredContent` payload renders as a namespaced `data-<ns>.<name>` part validated against the tool's `outputSchema`; the result is scanned before it re-enters the model; the toolset is built and closed per turn with a per-user credential. Sub-agents move off module singletons. |
| **P2. `veupathdb-wdk-mcp` and the suite** | ours | 1.5-2 EW | The sixteen tools of Section 3.1 are served over streamable HTTP; the conformance suite is a package a foreign team can run, and it is green against our own server; Claude Code can call it; the enrichment field names are a passing conformance case. |
| **P3. The reference Java server** | theirs, 3-6 EW; ours 0.5 to support | 3-6 EW | The suite is green against a `lib-jaxrs-container-core` service they deployed, driven by their Jenkins, publishing RFC 9728 protected-resource metadata, with the two-user isolation case passing. |
| **P4. The pilot assistant on the gene page** | joint, ours 2-3 EW | 2-3 EW | A researcher on a real record page gets an answer whose tools came over MCP, and an approval on a writing tool works end to end from the page. |
| **P5. The second server** | theirs | ~1 EW | The template holds: a second team ships a server without a PathFinder engineer in the loop. That is the same exit criterion the assessment set for its Phase 3, and it is the only one that proves the program. |

**Totals: ours 4-6 EW, theirs 3-6 EW.** The assessment priced WS4 at 2-3 ours plus 3-6 theirs; our half grows because two things were priced thin there - the conformance suite as a shipped package that a foreign team runs (it was "a skeleton"), and treating tool output as untrusted content, which is a real guard on a real call site and not a flag.

**Prerequisites that are not in the table but block P1.** `single_agent_graph` cannot currently resolve a deferred tool call, so an assistant on the simple shape that marks a tool approval-required gets an `error` chunk instead of an approval card (`assistant-platform/PROTOCOL.md` section 11, and `docs/knowledge/backlog/single-agent-graph-cannot-ask-for-approval.md`). The gene-page pilot is exactly that shape and Section 3.1 gives it a writing tool. This program makes that backlog item load-bearing; it must close before P4 and ideally during P1.

---

## Appendix A. What the library investigation found

Read on 2026-08-23 at `apps/api/.venv/lib/python3.14/site-packages/`. Versions: **pydantic-ai 2.22.0** (`pydantic_ai-2.22.0.dist-info`, `pydantic_ai_slim-2.22.0.dist-info`), **mcp 1.27.0**, **fastmcp-slim 3.3.1**.

| Question | Finding | Where |
|---|---|---|
| Which MCP revision? | `LATEST_PROTOCOL_VERSION = "2025-11-25"`. Note `DEFAULT_NEGOTIATED_VERSION = "2025-03-26"` for peers that do not negotiate. | `mcp/types.py` |
| How does `MCPToolset` connect? | Built on the FastMCP `Client`; accepts a URL, script path, `Path`, in-process `FastMCP` server, a `ClientTransport`, or a pre-built `fastmcp.Client`. | `pydantic_ai/mcp.py:671-713, 819-852` |
| Transports? | `_build_transport` returns `StreamableHttpTransport` for HTTP URLs, `SSETransport` when the URL infers SSE, and passes anything else to FastMCP's inference. `load_mcp_toolsets` builds `StdioTransport` from a `command` entry or an HTTP toolset from a `url` entry, one `MCPToolset` per server, each wrapped in `PrefixedToolset`. | `pydantic_ai/mcp.py:1470-1516, 1729-1779` |
| Where do annotations land? | `ToolDefinition.metadata = {'meta': mcp_tool.meta, 'annotations': mcp_tool.annotations.model_dump() or None, 'task': <bool>}`. Documented on the field itself. | `pydantic_ai/mcp.py:1155-1169`; `pydantic_ai/tools.py:604-608` |
| Approval hook? | `ApprovalRequiredToolset(wrapped, approval_required_func)` where the predicate is `(RunContext, ToolDefinition, dict) -> bool`; raises `ApprovalRequired` unless `ctx.tool_call_approved`. A `WrapperToolset`, so it composes over `MCPToolset` unchanged. | `pydantic_ai/toolsets/approval_required.py:22-32` |
| Does result-level `_meta` survive? | **No.** `_map_mcp_call_tool_result` reads only `structured_content` and `content`; `fastmcp`'s `CallToolResult` has a `meta` field that is never read. `_map_mcp_tool_result` carries an explicit comment that tool results do not preserve MCP annotations or `_meta`, only prompt content does. This is why Section 2.3 declares on the tool. | `pydantic_ai/mcp.py:1579-1594, 1610-1614`; `fastmcp/client/client.py:120-127` |
| Does tool-level `_meta` survive? | Yes, as `ToolDefinition.metadata['meta']`. | `pydantic_ai/mcp.py:1160` |
| Can a toolset emit a UI data part? | Yes. `ToolReturn` returned from any toolset's `call_tool` is unwrapped generically, and `iter_metadata_chunks` yields `DataChunk`, `SourceUrlChunk`, `SourceDocumentChunk` and `FileChunk` from its `metadata` onto the wire, dropping everything else. | `pydantic_ai/_tool_execution.py:564-588`; `pydantic_ai/ui/vercel_ai/_utils.py:171-188` |
| Long-running tools? | SEP-1686 task-augmented execution. `Tool.execution.taskSupport` in `{forbidden, optional, required}` resolves at `get_tools` into `metadata['task']`; `direct_call_tool(use_task=True)` sends `task=True` and awaits `tasks/result`. `prefer_tasks` defaults to `True`. | `pydantic_ai/mcp.py:733-738, 1154, 1186-1222` |
| Error behaviour? | `tool_error_behavior` in `{'retry' (default), 'error', 'failed'}`. Default converts a tool or protocol error into `ModelRetry` so the model self-corrects. Bare `McpError` is always recoverable, even under `'failed'`. | `pydantic_ai/mcp.py:719-725, 1230-1270, 1562-1576` |
| Per-call hooks? | `process_tool_call(ctx, call_tool, name, args)` may add request-level `_meta` via `call_tool(..., metadata=...)`, but it receives the **already-mapped** result, so it cannot recover dropped `_meta`. | `pydantic_ai/mcp.py:619-650, 1296-1300` |
| Timeouts? | `init_timeout` default 5 s; `read_timeout` default 300 s; `ToolDefinition.timeout` exists per tool and converts an overrun into a retry prompt. | `pydantic_ai/mcp.py:954-958`; `pydantic_ai/tools.py:610-615` |
| Cache invalidation? | The toolset installs its own message handler that invalidates the tools, resources and prompts caches on the corresponding `list_changed` notifications, then calls any user handler. | `pydantic_ai/mcp.py:1450-1467` |
| Capability wrapper? | `pydantic_ai.capabilities.MCP` pairs a provider-native MCP tool with a local `MCPToolset`. Its `authorization_token` is merged into headers at `_build_local` time, so it is per-construction, not per-run - the same constraint as `MCPToolset`. | `pydantic_ai/capabilities/mcp.py:28-46, 186-199` |

**MCP specification, revision 2025-11-25**, cited by section: Authorization (roles, RFC 9728 discovery, resource parameter per RFC 8707, access token usage, token audience binding, access token privilege restriction); Security Best Practices (confused deputy, token passthrough, SSRF, session hijacking, local server compromise, scope minimization); `ToolAnnotations` and `Tool.outputSchema` as implemented in mcp 1.27.0's `types.py`.

**MCP Java SDK**, read 2026-08-23: group `io.modelcontextprotocol.sdk`; latest **2.0.1**, major **2.0.0**; targets spec revision 2025-11-25; **Java 17+**; modules `mcp-bom`, `mcp-core` (STDIO, JDK `HttpClient` client, Jakarta Servlet server), `mcp-json-jackson2`, `mcp-json-jackson3`, `mcp`, `mcp-test`; Spring WebFlux and WebMVC transports moved to Spring AI 2.0+; SSE deprecated in favour of streamable HTTP; validated against the MCP conformance test suite 0.1.15.

## Appendix B. Found while reading, not fixed

Nothing in this appendix was changed. Each is a candidate backlog item.

> **Status, 2026-08-25.** Items 1 and 2 closed in batch A: every tool an
> instruction or an extractor names is registered, `update_search_decision` is
> deleted with its module, and an agreement suite fails on the next drift.
> Item 3 closed in batch B - the three sub-agents are per-dispatch factories.
> Item 4 had already closed before this program: the runtime owns the
> deferred-tool cycle and the backlog file that line cites no longer exists.
> Item 7 closed at PROTOCOL 1.1.0, and batch F4 took the card off the second
> dialect. Items 5 and 6 stand as written: MCP output passes a scan seam whose
> default is pass-through and no scanner is wired to it, and pydantic-ai still
> discards `CallToolResult.meta`, which is why a declared part is read from the
> tool's `_meta` and not the result's.

1. **Three standalone tools are defined but registered in no toolset.** `browse_search_categories` (`ai/tools/standalone/catalog.py:106`) and `list_transforms` (`catalog.py:147`) are named in `ai/context/extractors.py:197,199` - a tool-name list used by the context extractor - but neither appears in the FRAME, EXECUTION or VERIFICATION tool lists nor on the Lead. The extractor therefore lists tools that can never produce an observation. `update_search_decision` (`catalog_selection.py:44`) is referenced nowhere outside its own module.
2. **The VERIFY agent's instructions name two tools it cannot call.** `ai/agents/verification.py:65-68` tells the model to resolve gene names via `literature_search` then `lookup_gene_records` then `resolve_gene_ids_to_records` before passing controls. The verification toolset (`ai/tools/toolsets/verification.py:93-122`) contains none of those three, and `resolve_gene_ids_to_records` (`gene.py:45`) is in no toolset at all. A model that follows the instruction gets a tool-not-found retry. Costs at least one wasted model turn whenever controls are needed, and it is a plausible contributor to control-test friction.
3. **The three sub-agents are module-level singletons with toolsets baked at import** (`ai/agents/frame.py:131`, `execution.py:179`, `verification.py:147`), while the Lead is built per turn (`ai/agents/registry.py`). A per-user, per-turn MCP toolset cannot reach a singleton. Named as P1 work rather than a defect, but it is the concrete blocker.
4. **`single_agent_graph` cannot ask for approval**, so an assistant on the simple shape that marks a tool `requires_approval=True` receives an `error` chunk instead of an approval card (`assistant-platform/PROTOCOL.md` section 11; `docs/knowledge/backlog/single-agent-graph-cannot-ask-for-approval.md`). This program makes it load-bearing: the recommended pilot is exactly that shape and Section 3.1 gives it a writing tool.
5. **Tool output is still unscanned.** PIGuard runs on the last user message (`ai/conversation/dispatcher.py`) and web-search page text enters the context unchecked. Assessment gap 7, still listed as open in the status addendum. Section 2.5 turns it from a latent risk into a requirement.
6. **pydantic-ai discards `CallToolResult.meta`.** Not a defect in this repository, and arguably not one upstream either, but it is a real constraint that shaped Section 2.3 and it is worth an upstream issue: the FastMCP client parses `meta` and the mapper never reads it.
7. **The durable-task SSE dialect is still separate** from the v6 chunk vocabulary, which means any non-JS consumer implements two protocols (Section 6.4). Assessment 2.2 finding 6, unchanged.

## Appendix C. Drift from the assessment's line references

The assessment froze its line numbers on 2026-08-17 and warned they would drift. They have. Anyone planning from Appendix A or B of that document should read this first.

| Assessment claim | Today |
|---|---|
| Entanglement 1: `ai/graph/state.py:147-184`, checkpointed `PipelineState` carries science, `extra="forbid"`, no slot for another product | Closed. `class PipelineState(TurnState)` at `ai/graph/state.py:114`, with the science in `StrategyDomainState` at `:95`. |
| Entanglement 3: `ai/conversation/serde.py:29-43` enumerates 8 science types | Moved. The serializer is `assistant-platform/packages/assistant-core/src/assistant_core/conversation/serde.py`; the allowlist is the union of the registered assistants' `checkpoint_types`. |
| Entanglement 4: `persistence/models.py:194-258`, `Conversation` is thread and strategy | Closed. Split into a thread plus a 1:1 `conversation_strategies` attachment. |
| Entanglement 8: closed `data-*` union on both sides | Closed. Open registry at `assistant_core/conversation/stream_parts/registry.py`; the schema index now lives at `transport/http/routers/_stream_parts_schemas.py`. |
| Entanglement 15: dead `_is_approval_reply` in `ai/conversation/dispatcher.py:80-87` | Deleted; no occurrence remains. |
| `ai/memory/` package | Moved to `assistant_core/memory/`. |
| Entanglement 5: `ai/agents/roles.py:7-12` leaks `PhaseRole` | Still present at `ai/agents/roles.py`; WS2 made roles an injected seam but the module remains. |
| Appendix B: "own agent", "own deps", "own domain state", "own mock", "own identity" hard-coded | All five are now `AssistantSpec` declarations (`assistant-platform/packages/assistant-core/src/assistant_core/spec.py:116-133`). |
| Section 3.3: "expose PathFinder's WDK toolset as `veupathdb-wdk-mcp` so a consumer can call `find_searches`, `read_param_options`, `run_search`, `lookup_gene`" | Directionally right, names approximate. Section 3.1 of this document gives the measured inventory: the catalog and record reads export cleanly, `run_search` in the sense of building a step does not, and four tools split into a service half and a discovery-gate half that stays here. |
