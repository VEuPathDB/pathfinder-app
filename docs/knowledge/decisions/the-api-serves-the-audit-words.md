---
type: Decision
title: The API serves the audit words, and the web holds only words no backend table holds
description: Every audit word with a backend table in `domain/audit/words.py` reaches the web from the API, on a finding (`checkTitle`, `errorTitle`, `verdictText`) or from `GET /api/v1/audits/words` when no finding is at hand; the web keeps a table only for a value no backend table names. A TypeScript copy of each backend table held equal by a test was rejected.
tags: [audit, web, words, openapi]
generated: { by: claude-code/opus-5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What was decided

**One source per word.** `domain/audit/words.py` holds the words of the checks
(`CHECK_TITLES`), the error types (`ERROR_TYPE_TITLES`,
`ERROR_TYPE_DESCRIPTIONS`), a finding's status (`UNCHECKED_SENTENCES`), the
unresolved count by status (`UNRESOLVED_WORDS`), why a run halted
(`HALT_SENTENCES`), and a review's verdict, literature status and progress.
A page shows the words a finding carries when it has the finding. When it has
no finding (a filter label, a legend, a count by status, a halted run), it reads
`GET /api/v1/audits/words`.

**A typed response.** `services/audit/words.py::AuditWords` holds one model per
table, each with one field per value, so the spec and the Kubb types name every
key, and the web reads `words.checks[check]` with no missing case. Each table is
built with `model_validate` from the dict in `words.py` under `extra="forbid"`,
so a value with no words, or words for a value that does not exist, fails at
import. `packages/spec/audit_words.json` is the body the route serves. An api
test holds it equal to the route, and the web tests read it as the response.

**What the web keeps.** `features/audit/words.ts` holds words only for values
with no backend table: certainty, a genome's and a piece of evidence's status,
the evidence kinds, the stages, the genome roles, the run phases, the
importance and use sources, and where a finding came from.

# Rejected

**A TypeScript copy of each backend table, held equal by a test.** The two
copies can still drift between a backend change and the test that catches it,
and every new table needs a second copy and a second test. The page and the CSV
then read different sources for one sentence.

**`dict[Literal, str]` fields in the response.** The spec keeps the key type as
`propertyNames`, but the generated types read it as `{[key: string]: string}`,
so a lookup in the web can come back undefined.
