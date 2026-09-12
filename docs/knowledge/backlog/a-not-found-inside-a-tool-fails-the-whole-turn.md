---
type: Backlog
---

# A not-found inside a tool fails the whole turn

**What I did.** Through the web UI on plasmodb, the user asked to save 155 genes as a gene set and run one EDA analysis. The Lead called `import_control_ids_from_gene_set(gene_set_id="d6edd975-f6d9-482e-bc50-3d666b55227f")` with an id no gene set has.

**What I got.** The turn ended with `Response failed: Resource not found: Gene set not found: d6edd975-...` and a "Try again" control; the trace row reads `Controls from gene set: Tool execution was interrupted by an error`. The worker log: `error_type: NotFoundError ... pydantic-ai stream raised; converting to chat-visible ErrorChunk` (`assistant_core.conversation.vercel_adapter`). The EDA subset the turn had already opened and the figure it had drawn were left without a reply.

**Why that's wrong.** One wrong id, which the model could have corrected by listing gene sets, discards the whole turn's work and shows the user a failure instead of an answer.

**Why it happens.** `ai/tools/standalone/control_sets.py:7-15` calls `control_ids_from_saved_gene_set`, whose `NotFoundError` (an `AppError`) escapes the tool body; the runtime treats an exception from a tool as a stream failure.

**Fix.** A tool that takes a caller-supplied id answers a missing one with a `ModelRetry` naming the tool that lists valid ids; and one wrapper at the tool layer converts every `AppError` a tool body raises into a tool error the model reads, so no service refusal becomes a turn failure. Red first with the measured id.

**What you'd get.** The model is told the id is unknown and which tool lists gene sets, lists them, and continues; the turn ends with an answer.
