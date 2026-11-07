---
type: Decision
title: Explore reads the account with the researcher's leave
description: Explore reads the thread's strategy freely and the researcher's saved strategies, other threads and gene set genes only after an ask card the researcher allows, once, for the thread or for every thread; a per-thread checkbox in the right rail, a consent asked once per thread and Build reading the account were rejected.
tags: [explore, privacy, consent]
generated: { by: claude-code/opus-5.5, at: 2026-11-07T00:00:00Z }
status: stable
---

# What was decided

Explore reads the strategy its thread holds with no ask. To read the researcher's saved
strategies (`read_saved_strategies`), their other PathFinder threads (`list_my_threads`,
`read_my_thread`, the latest 20 exchanges, redacted as an eval extract is) or a gene set's genes
(`read_gene_set`, the first 500), it calls `ask_to_read_the_account(what)` first
(`ai/explore/account_reads.py`). That tool always needs approval, so the thread parks a card
(`content/parts/AccountReadCard.tsx`) that names `what` and offers Allow and Don't allow, with two
checkboxes: "Always allow in this conversation" (`conversation_account_reads`, `PUT
/api/v1/conversations/{id}/account-reads`) and "Always allow in all conversations"
(`users.account_reads_always`, `GET`/`PUT /api/v1/me/account-reads`, also a switch in Settings,
Privacy). The card saves a ticked allowance before it sends the approval. An allowed ask lets the
reads of that turn run (`TurnMarkers.account_reads_allowed`); a standing allowance lets every read
run with no ask; any other read is refused back to the model with "call ask_to_read_the_account
first". Don't allow stores nothing, so Explore may ask again later. Build has none of these tools.

# Why

Another thread or a saved strategy can change an answer, and it is the researcher's own work, so
the researcher decides each time unless they say to stop asking. The thread's own strategy is
what the conversation is about, so reading it asks nothing.

# What was rejected

- **A checkbox in the right rail for each thread.** The researcher sees the question when Explore
  wants to read, with what it wants to read, not as a setting to find beforehand.
- **One consent per thread.** Asking at each read, with an always-allow, keeps a single read from
  opening every later one.
- **Build reading the account.** Build keeps its tools; the reads serve research in Explore.
