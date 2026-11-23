---
type: Decision
title: A conversation is shared by a link
description: The owner of a conversation can make one link that shows it read-only and live, open to anyone with the link or behind a generated password, with an optional copy into the viewer's own account; snapshot links, owner-typed passwords and copies that stay branches of the source were rejected.
tags: [conversations, sharing, privacy]
generated: { by: claude-code/opus-5.5, at: 2026-11-09T00:00:00Z }
status: stable
---

# What was decided

A conversation has at most one share link (`conversation_shares`, keyed by the conversation).
The owner makes, changes and ends it from the Share button at the top of the conversation
(`PUT`, `GET`, `DELETE /api/v1/conversations/{id}/share`). The link names a random token and
opens `/shared/<token>`, inside the website that frames Strategist.

- **Who can open it.** With "Anyone with the link can open it" ticked, the token is enough.
  Otherwise the link needs a password Strategist generates (`POST .../share/password` makes a new
  one, which locks out the old). The password is shown once and stored as its SHA-256; the
  viewer's page sends it in the `X-Share-Password` header.
- **What a viewer sees.** The thread as its owner sees it, read-only: the messages, the trace,
  the figures and the cards, with every control that acts (branch, edit, rate, regenerate,
  approve, Build it, save, publish, delete, open the study, open a memory) left out. With
  "Include the strategy and its context" ticked (`conversation_shares.include_context`, on for a
  new link), `GET /api/v1/shared/{token}/context` serves the thread's strategy and its bound study
  for a read-only rail; it refuses with 403 `SHARE_CONTEXT_NOT_SHARED` when the box is cleared.
  It is redacted once, in `services/conversations/shared_context.py`: the owner's WDK handles
  (strategy and step ids, the WDK and study links, the gene set id), the spend and the thread
  ids are withheld, and the conversation id is one derived from the token. Which step inputs are
  account data is one rule in `domain/private_inputs.py`, keyed on the WDK parameter kind: a
  dataset input (an uploaded list, a gene set, a basket, a file) and a value whose kind was never
  read are withheld and named in `privateInputs`, and a step input (an owner step id) is
  withheld always. A study on the owner's own upload (an `EDAUD_` dataset) is account data by
  the same rule. Every field derived from the inputs follows it, against the values withheld
  anywhere in the strategy, not only on the step itself: a step's reason is cleared when it
  names a withheld value or an upload (`for_viewer` on each reason type), and keeps only the
  shown inputs it was derived from; a filter or step-analysis value has no parameter kind, so it
  is withheld unless the account box is ticked and it names no withheld value. The site's own words are never shown: a failed
  push reads "This step failed on the site.", and a validation keeps its outcome without its
  messages, since WDK quotes the values it refused in them. The study is the newest state the thread showed of the bound analysis; a study
  no turn showed is not shared. The owner's notes and tasks are not shared. A viewer needs no
  sign-in. A tool that
  read outside the thread (`domain/owner_reads.py`: the owner's WDK strategies, saved strategies,
  other threads, gene sets, control sets, audits, memories and download links) keeps its call and
  loses its output, and a turn's recalled memories are emptied, both in what the link serves and
  in a copy, unless the owner ticks "Include what it read from your account"
  (`conversation_shares.include_account_reads`, off by default). A copy drops the owner's
  control sets and gene sets from its saved state either way, since they work only in the
  owner's account. A test classes every tool an agent carries as an owner read or not, so a new tool
  cannot slip past. A study the owner uploaded (an `EDAUD_` dataset,
  `domain/account_datasets.py`) is account data too. Its id, and the study and analysis ids and
  names that any chunk naming a mark gives it, gathered until no new one appears, are its marks;
  every string and key in a chunk is tested as it is, never as escaped JSON. A call that names a
  mark keeps its call and loses its contents; a data part that names one is left out; a text or
  reasoning block whose joined text names one reads only "This part names a private dataset and
  is not shared."; and any other chunk that names one has every mark in it replaced.
- **Live.** The page asks `GET /api/v1/shared/{token}` every few seconds for the end of the
  thread's completed history and whether a turn is running, and reads the thread again
  (`GET /api/v1/shared/{token}/snapshot`) when that end moves. A running turn shows as a line
  that the owner's conversation is answering, and the turn itself appears when it completes.
- **Copying.** With "Let viewers copy it" ticked, a signed-in viewer can make a copy
  (`POST /api/v1/shared/{token}/copy`). The copy is a branch of the whole thread made for the
  viewer's account: the viewer's own WDK strategy and study document, the owner's notes and
  history up to the copy, and no parent link, so the owner's thread tree and its cascading
  delete never reach the viewer's copy. The copy's saved state is rewritten for its new account
  (`assistants/copies.py`): `StrategyDomainState.for_another_account` drops the owner's control
  sets, attached controls, separation offers, gene sets and memory counts, and the recalled
  memories are emptied. Only Strategist's own threads can be copied. A copy waits for a settled
  thread, and its refusals speak to the viewer.
- **Links made before the context box.** A link made before the box existed keeps the context
  out, since its owner never saw the box; the head (`GET /api/v1/shared/{token}`) says whether a
  link carries it and names the strategy revision, so a viewer reads the context again when the
  owner edits the strategy with no new turn.
- **Ending it.** Stop sharing deletes the row; the old link then answers 404. Deleting the
  conversation deletes its link.

# Why

Researchers send a conversation to a colleague to show how an answer was reached. The colleague
reads it where it was written, sees it continue, and takes their own copy to work from. A
generated password keeps a link that is pasted somewhere public from opening it, without asking
the owner to invent a secret.

# What was rejected

- **A snapshot taken when the link is made.** The owner wants the colleague to see the thread
  continue; a frozen copy would need a new link after every turn.
- **Streaming a running turn to the viewer.** It needs the event tail behind a share token and a
  second chat runtime on the page; a completed turn a few seconds late serves a reader.
- **A password the owner types.** A generated one is long enough that the share routes need no
  attempt limit.
- **A copy that stays a branch of the source.** A branch hangs under its source and is deleted
  with it; a copy belongs to another account and must outlive the owner's thread.
- **Extending the snapshot route.** `EventsSnapshot` is the runtime's wire model in
  `assistant_core`, so Strategist-only state on it would need a library change, and it would be
  read again with every cursor move.
