---
type: Procedure
title: UAT runner checklist
description: The order a runner follows for one site in one sitting, with the time each block took when measured, the data-hygiene sweep that ends the sitting, and the bug template.
tags: [uat, runner, checklist, bug-template]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Runner checklist

Times are the measured wall time of the same turns with `openai:gpt-5.6-luna` at `medium` effort (2026-09-24), plus about a minute of reading per flow; a turn's cost is the composer's usage pill. Record every result in [the UAT index](index.md) as you go.

## Once, before the first site (about 30 min)

1. Deployment checks D1 to D11 ([deployment](flows-deployment.md)). A failure stops the run.
2. Read the five `buildNumber`s (D8) into the index.
3. Two clean accounts A and B, two browser profiles, each signed in to the five sites too ([sites and accounts](sites-and-accounts.md)).
4. The test files of [composer flows](flows-composer.md).

## One component site (core only: about 30 min, about $0.50)

| Order | Flows | Measured wall time | Measured cost |
|---|---|---|---|
| 1 | F1, F2 | 5 min | - |
| 2 | S1 with V1 | 2 min (101 s) | $0.074 |
| 3 | S2 with V1 | 2 to 4 min (56 to 236 s) | $0.05 to $0.14 |
| 4 | S5 (plasmodb, toxodb, vectorbase, fungidb, portal as X5) | 3 to 4 min (149 to 236 s) | $0.09 to $0.38 |
| 5 | G1 | 1 min (17 s) | $0.012 |
| 6 | X2 (read the traces of steps 2 to 4) | 2 min | - |
| 7 | F4, F7 cleanup of the site | 5 min | - |

## plasmodb, the full run (about 5 h, about $4)

| Order | Flows | Measured wall time |
|---|---|---|
| 1 | Core of the table above | 20 min |
| 2 | F4 to F11 | 35 min (F10 runs S2 twice, F11 waits 3 min) |
| 3 | S3, S4, S6, S7, S8 | 25 min (140 s, 137 s, 205 s; S7 and S8 are clicks) |
| 4 | S9 to S16 | 25 min (128 s, 141 s, $0.05 turns, 164 s, 10 to 14 s, 102 s, 31 s) |
| 5 | N1 to N12 | 30 min (N1 up to 5 min; most under 2 min) |
| 6 | V2, V3, V4, V5 | 35 min (V2 measured 521 s, V4 run 135 s plus its turns; V3 up to 15 min when it runs) |
| 7 | E1 to E5, E8 | 25 min (E2 146 s) |
| 8 | E6, E7 (needs the count matrix) | 20 min (install about 68 s) |
| 9 | M1 to M6 | 20 min |
| 10 | C1 to C16 | 25 min |
| 11 | A1, A3, A5, A6 (A2 where keys are on) | 20 min |
| 12 | G2, G3 | 10 min |
| 13 | X1, X6 | 10 min (127 s) |
| 14 | L1 to L5 | 20 min |
| 15 | F12 with account B | 15 min |
| 16 | R1, R4 with the operator; R2, R5, R6, R7 | 45 min (R5 about 30 turns) |
| 17 | H1 | 10 min |

## H1 - The data-hygiene sweep (end of every sitting)

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Sidebar of each site | Delete every UAT conversation with `Also delete strategy from <site name>` ticked; then `Dismissed (<n>)`, `Delete permanently` each | No UAT row left, no `Dismissed` section |
| 2 | Nav rail `Saved strategies` | `Delete saved strategy` on each UAT row | `No saved strategies yet.` |
| 3 | Settings, `Memory` | Delete every row UAT wrote (confirm each) | Every section `No items stored yet.`, or only rows that predate UAT |
| 4 | Composer | `/export`, `Latest gene set on this site (CSV)` on each site | `No gene sets to export.` |
| 5 | Each VEuPathDB site, signed in as the account | My Strategies; My Data Sets; the study analyses | No strategy, dataset or analysis UAT made. PathFinder never deletes datasets or analyses: delete them there |
| 6 | A dedicated UAT account only | Settings, `Data`, `Clear ALL data + VEuPathDB`, type `delete my data`, `Confirm` | Toast `Data cleared`; steps 1 to 4 read empty again |

## Bug template

The six headings of the engineering bug format. A runner who is not an engineer fills the first three; the last three are optional and the engineer who takes the bug writes them.

```
Title: <one line: what is wrong, where>
Flow: <id>   Site: <id>   Build: <buildNumber>   Date: <UTC>   Account: <A or B>
Severity: <blocker | major | minor>

1. What I did - the exact steps and messages, with the numbers used.
2. What I got - the output, quoted; the conversation URL; a screenshot; the
   expected value beside it.
3. Why that's wrong - what ends up wrong for a researcher (a count, a saved
   result, an export).
4. Why it happens (optional) - one sentence naming the file or symbol.
5. Fix (optional) - what changes.
6. What you'd get (optional) - the output after the fix.
```

Attach the conversation's `/export` JSON for every `fail`. Never paste a credential, a token or an account id.
