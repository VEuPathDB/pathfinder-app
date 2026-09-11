---
type: Backlog
title: The web never sends an assistant id, so no front end reaches the second assistant
description: The backend serves two assistants and refuses a mismatch, but buildChatRequestBody sends siteId, phaseModels and phaseReasoning and nothing else, so every thread the app creates is answered by pathfinder and site_help is unreachable from the product.
tags: [web, assistants, site-help, chat, generality]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What I did

Read the body the chat transport builds
(`apps/web/src/features/conversation/runtime/buildRequestBody.ts`), searched the
whole web tree for the field (`rg assistantId apps/web/src`), and listed the
generated types that carry it.

# What I got

`buildRequestBody.ts:37-41` passes one `extra` object:

```
extra: {
  siteId: args.siteId,
  phaseModels: args.phaseModels,
  phaseReasoning: args.phaseReasoning,
},
```

The search returns five hits, all in `features/conversation/RevertFlow.test.tsx`,
where `assistantId` is a local variable holding an assistant message id. Four
generated types declare the field the web never writes or reads:
`BeginConversationRequest.ts:19`, `OpenConversationRequest.ts:14`,
`ChatRequestBody.ts:39`, `ConversationResponse.ts:26`.
`apps/api/src/pathfinder/assistants/registry.py:18` installs two specs,
`build_pathfinder_spec()` and `build_site_help_spec()`.

# Why that's wrong

The second assistant is built, registered, gated, tooled and served, and no
user can open a thread with it. Every conversation the product creates takes
the registry default, so `site_help` answers nobody, the 409 mismatch rule is
unexercised by any client, and the one piece of evidence that the runtime seam
carries a second product is a seam nothing crosses.

# Why it happens

`buildChatRequestBody` names three extra fields and no assistant, and no store
holds an assistant selection to name.

# Fix

In this repository, `apps/web`. Hold the chosen assistant in session state,
add it to the `extra` object in `buildChatRequestBody`, send it on the create
calls that carry `BeginConversationRequest` and `OpenConversationRequest`, and
read `ConversationResponse.assistantId` back so a thread shows which assistant
answers it. No library change: the wire field already exists in the spec and in
the generated types.

# What you'd get

A thread opened against `site_help` runs the one-agent graph, and a request
that names another assistant on that thread is refused 409 by the rule that
already exists. Both assistants are reachable from the product, and the next
assistant is a registration plus a menu entry.
