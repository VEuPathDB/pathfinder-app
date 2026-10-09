---
type: Decision
title: Nothing is copied for review until the researcher has seen the data notice for the current statement
description: Learning from a researcher's strategies stays on by default, but extraction and the copy on dislike both require users.data_notice_seen to equal the statement version the api serves, and the first signed-in visit shows a notice that records that version and the learning choice in one call. An opt-out with no notice and an opt-in default off were rejected.
tags: [privacy, evals, consent, persistence, web]
generated: { by: claude-code/opus-5, at: 2026-10-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-09T00:00:00Z }
status: stable
---

# What was decided

**The statement has one version, owned by the api.**
`domain/data_statement.py::DataStatementVersion.CURRENT` is the date the data
statement was last updated (`2026-10-09`). It reaches the web through the OpenAPI
spec: `@pathfinder/shared` exports `DATA_STATEMENT_VERSION` from the generated
`dataStatementVersionEnum`, and `/help/your-data` prints it as "Last updated". A
change to the statement changes this one value and regenerates the types, so the
page date and the gate cannot disagree.

**An account records the version it saw.** `users.data_notice_seen` (alembic
`2026_10_09_0002`) holds the version string; it replaced `eval_notice_seen_at`,
and no account carries a seen version over, because no earlier notice said what
the statement says. `GET /api/v1/me/privacy` returns `evalDataConsent`,
`dataNoticeSeen` and the computed `noticeDue`. `POST
/api/v1/me/privacy/data-notice` takes `{version, evalDataConsent}`: the version is
typed as the enum, so a version the api does not serve is a 422, and an unticked
box clears the staged copies in the same transaction, as the Privacy tab does.

**The gate is one SQL expression.** `services/eval_data/consent.py::copies_allowed`
is consent AND `data_notice_seen` equal to the current version. The nightly
extraction (`extraction.py::_candidate_query`) and the copy on dislike
(`rated.py::_extract_through`) both select it, so an account that has not seen
the current version is treated as not consenting, including every account that
existed before this change and every account after the next statement change.

**The notice is the shell's.** `features/help/DataNotice.tsx` mounts in
`app/[siteId]/(app)/layout.tsx`, opens once the session is refreshed and signed
in and `noticeDue` is true, and closes only on Continue. It shows the same seven
points as the page's In brief (`features/help/yourDataBrief.ts`), a link to the
full statement in a new tab, and the learning checkbox ticked.

# What was rejected

**Opt-out with no notice.** The switch was on by default and a researcher who
never opened the Privacy tab never learned that a person may read their
conversations. A default the researcher has not been shown is not a choice.

**Opt-in, default off.** The copies are the eval corpus that keeps the product
honest, and a default off yields almost none. The notice shows the choice once,
before anything is copied, with the box ticked and one line saying what it means
and where to change it; that keeps the choice the researcher's without making it
an extra step.

**The version in the web only.** The web would date the page and the api would
gate on another constant, so the two could drift. A public read of the version
was rejected because the page is a static route outside the app shell, and the
generated enum gives the web the same value at build time.
