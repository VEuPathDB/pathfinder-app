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
opens `/shared/<token>`, inside the website that frames PathFinder.

- **Who can open it.** With "Anyone with the link can open it" ticked, the token is enough.
  Otherwise the link needs a password PathFinder generates (`POST .../share/password` makes a new
  one, which locks out the old). The password is shown once and stored as its SHA-256; the
  viewer's page sends it in the `X-Share-Password` header.
- **What a viewer sees.** The thread as its owner sees it, read-only: the messages, the trace,
  the figures and the cards, with every control that acts (branch, edit, rate, regenerate,
  approve, Build it, save, publish, delete, open the study, open a memory) left out. The owner's
  side panels, strategy, notes and tasks are not shared. A viewer needs no sign-in. A tool that
  read outside the thread (`domain/owner_reads.py`: the owner's WDK strategies, saved strategies,
  other threads, gene sets, control sets, audits, memories and download links) keeps its call and
  loses its output, and a turn's recalled memories are emptied, both in what the link serves and
  in a copy. A test classes every tool an agent carries as an owner read or not, so a new tool
  cannot slip past.
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
  memories are emptied. Only PathFinder's own threads can be copied. A copy waits for a settled
  thread, and its refusals speak to the viewer.
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
- **Sharing the side panels.** They read the owner's strategy, notes and tasks through
  owner-only routes; the copy gives the viewer all of them in their own account.
