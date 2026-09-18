---
type: Decision
title: A staged eval case carries its user until promotion, and a promoted case carries nobody
description: The two frozen rules - extraction severs user linkage, and an opt-out clears the user's staged items - cannot both hold if a staged row names nobody. The resolution is that the association lives on the queue row and ends at promotion, enforced by a check constraint; the corpus file that survives names a site, an assistant and a random staging id. Storing no linkage at all was rejected because nothing could then be cleared; keeping it after promotion was rejected because the corpus is what ships.
tags: [ws-v, evals, privacy, persistence, consent]
generated: { by: claude-code/opus-5, at: 2026-08-23T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-23T00:00:00Z }
status: stable
---

# The tension

Two governance rules were ruled together and read as contradictory:

- Raw data never enters the corpus: extraction severs user linkage into a
  staging queue.
- An opt-out stops extraction **and clears the user's staged items**, and the
  account purge clears them too.

A row that names nobody cannot be found when that person opts out. A row that
names somebody has not severed anything. Both cannot be true of the same row at
the same time.

# What was decided

The linkage has a lifetime, and promotion is when it ends.

`eval_staged_cases` holds a candidate between extraction and curation. While
its `status` is `staged` it carries `user_id`, `source_conversation_id` and the
`extract`, so an opt-out and a purge can delete it and a curator can read it.
Promotion writes the case into the repo corpus and then nulls all three, leaving
`status = 'promoted'`, the `content_hash`, the `corpus_name`, the site and the
assistant.

The rule is a check constraint, not a convention:

```
(status = 'staged'   AND user_id IS NOT NULL AND source_conversation_id IS NOT NULL AND extract IS NOT NULL)
OR
(status = 'promoted' AND user_id IS NULL     AND source_conversation_id IS NULL     AND extract IS NULL)
```

A promotion that kept the user cannot be written. The foreign keys cascade, so
deleting the account removes every staged row of that account without any code
running, while promoted rows are already unreachable from it.

The corpus file carries `CaseProvenance`: site, assistant, origin, the date, and
the random staging id. The staging id addresses a row that no longer names
anyone, so it is a reference into the audit trail and not a handle on a person.

**Idempotency without a back-reference.** Extraction must not re-queue a case it
already queued or promoted. The `content_hash` of the redacted extract is what
survives promotion, and it is unique across the table, so a promoted case cannot
return. Staged rows additionally carry a unique `source_conversation_id`, so the
same thread does not queue twice while it waits. This is the shape
`memory_tombstones` already uses to keep a deleted memory from being re-written.

**Redaction is two-stage, and the first stage only removes what is never
science.** `pathfinder.evals.redaction` strips email addresses and URL
credentials, and `EvalExtract` refuses to be constructed if either pattern
survives, so an unredacted extract cannot reach the queue. No rule reads digits:
in this domain a digit run is a gene count, a threshold or a WDK strategy id,
and a false positive would silently corrupt a case. The full redaction is the
human curation step, which is where the ruling put it.

# What was rejected

**Store no linkage at all, and accept that an opt-out cannot clear.** It makes
the queue unaccountable: a user who turns the switch off is told their staged
items are gone and they are not. The rule that was ruled is the stronger one.

**Keep `user_id` after promotion so the audit trail is complete.** The corpus is
what ships, gets copied, and outlives the account. A promoted case is
de-identified science or it is not promotable.

**Delete the staged row at promotion instead of blanking it.** Then the content
hash goes with it and the next extraction pass re-queues the same investigation,
so the curator sees a duplicate of something already in the corpus. Keeping a
hash-only row is the smallest thing that keeps promotion final.

**A separate `eval_extraction_marks` table keyed by conversation.** It works,
and it adds a table whose only job is to remember a decision the hash already
remembers. It also survives an opt-out unless it is cleared too, which makes
re-consent behave differently from first consent for no stated reason.

# Consequences

- Opting out is symmetric: consent off clears the queue, consent on lets the
  same threads be extracted again. The integration suite states both.
- `DELETE /api/v1/user/data` reports `stagedEvalCases` beside the other counts,
  so a purge says what it removed. It removes only the calling application's
  rows, and only the named site's when the request names a site; the consent
  opt-out is the one that clears every one of the user's, because that decision
  is the account's.
- A curator can always answer "where did this case come from" with a site, an
  assistant and a date, and can never answer "who wrote it".
- The corpus location is `apps/api/src/pathfinder/evals/corpus/`, inside the
  package that defines the case shape, so the loader resolves it without a path
  convention and the cases ship with the code that reads them.
