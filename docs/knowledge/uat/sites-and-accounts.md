---
type: Reference
title: UAT sites and accounts
description: The five sites UAT runs on and why, the build each expected number was measured on, what a runner needs before the first click, and the rule that every flow deletes what it created.
tags: [uat, sites, accounts, data-hygiene]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# UAT sites and accounts

## The five sites

| Site id | Name in the site menu | Service base | Why it is in UAT |
|---|---|---|---|
| `veupathdb` | `VEuPathDB Portal (All organisms)` | `https://veupathdb.org/veupathdb/service` | The entry site; the only site where one strategy holds two genera (cross-genus orthology). |
| `plasmodb` | `PlasmoDB (Plasmodium)` | `https://plasmodb.org/plasmo/service` | The site the corpus, the seeds and the e2e suite measure first; most flows are specified here. |
| `vectorbase` | `VectorBase (Vectors)` | `https://vectorbase.org/vectorbase/service` | Insect hosts, not parasites: different searches, 98 organisms, the largest result sizes of the five (2,928 signal-peptide genes). |
| `toxodb` | `ToxoDB (Toxoplasma)` | `https://toxodb.org/toxo/service` | A second apicomplexan genus with its own clades on the orthology sheet (Eimeriidae, Sarcocystidae), so a Plasmodium organism named here must be refused toward the portal. |
| `fungidb` | `FungiDB (Fungi)` | `https://fungidb.org/fungidb/service` | Fungi: the largest organism sheet of the five (317 organisms on `GenesWithSignalPeptide`), a different kingdom, and the longest catalog load. |

`tritrypdb` is the alternate for `fungidb`: it carries the corpus case `question-turns-do-not-build`, but its data is closer to the apicomplexan sites than fungi are.

## Build numbers

Read with `curl -s https://<host>/<project>/service/` (field `buildNumber`). Every expected number in the family documents was measured on this build.

| Site | `buildNumber` | `releaseDate` | Read on |
|---|---|---|---|
| veupathdb | 71 | 20 August 2026 | 2026-09-24 |
| plasmodb | 71 | 20 August 2026 | 2026-09-24 |
| vectorbase | 71 | 20 August 2026 | 2026-09-24 |
| toxodb | 71 | 20 August 2026 | 2026-09-24 |
| fungidb | 71 | 20 August 2026 | 2026-09-24 |

At UAT start the runner reads the five numbers again and writes them in [the UAT index](index.md). A different number switches the count rule to "new build" in [exit criteria](exit-criteria.md).

## Baseline counts per site

The seed every site's core flows share: "genes of organism X with a predicted signal peptide and 2 to 99 transmembrane domains", then its orthologs in organism Y. Measured on build 71, 2026-09-24, by building each tree as a strategy under the dev login and reading `estimatedSize` (which counts genes; the report's `totalCount` counts transcripts). Parameters: `GenesWithSignalPeptide` `signalp_version=SignalP-6.0`; `GenesByTransmembraneDomains` `min_tm=2`, `max_tm=99`; `GenesByOrthologs` `isSyntenic` as stated.

| Site | Organism X | Signal peptide | 2-99 TM | INTERSECT | Organism Y | Orthologs, `isSyntenic=no` | Orthologs, `isSyntenic=yes` |
|---|---|---|---|---|---|---|---|
| plasmodb | Plasmodium falciparum 3D7 | 479 | 840 | 116 | Plasmodium vivax P01 | 142 | 67 |
| vectorbase | Anopheles gambiae PEST | 2,928 | 1,871 | 343 | Aedes aegypti LVP_AGWG | 850 | 235 |
| toxodb | Toxoplasma gondii ME49 | 720 | 946 | 78 | Neospora caninum Liverpool | 145 | 69 |
| fungidb | Aspergillus fumigatus Af293 | 748 | 1,341 | 64 | Aspergillus nidulans FGSC A4 | 257 | 50 |
| veupathdb | Plasmodium falciparum 3D7 | 479 | 840 | 116 | Toxoplasma gondii ME49 | 87 | 0 |

The default of `isSyntenic` on every site is `no`. A request that does not say "syntenic" expects the `no` column.

## What a runner needs

| Item | Detail |
|---|---|
| The test deployment | `<pathfinder-url>`, and whatever network access its operator requires (a VPN or a tunnel). |
| Account A | A registered VEuPathDB account used only for UAT. PathFinder refuses guests: a request without a registered login answers 401 `WDK_LOGIN_REQUIRED`. |
| Account B | A second registered VEuPathDB account, used only for the isolation flows (`F12`). It must be a different VEuPathDB user than A. |
| Two browser profiles | One per account, so the two sessions never share a cookie. |
| The same account on the site | Sign in to each of the five sites with the account in use, in the same profile, so every `Open in <Site>` link shows the strategy. |
| A clean start | Both accounts start with no PathFinder data. On a dedicated UAT account: Settings, `Data` tab, `Clear ALL data + VEuPathDB`, type `delete my data`, `Confirm`. A leftover memory changes what the assistant recalls, so a flow run on a used account is not comparable. |
| Test files | The attachment files listed in [composer flows](flows-composer.md). |

The engineering dev account is named in the gitignored `.env.dev` as `WDK_DEV_EMAIL` and `WDK_DEV_PASSWORD`; the service token there is `VEUPATHDB_AUTH_TOKEN`, and it resolves to the same VEuPathDB user as the dev email, so it cannot serve as account B. Never paste a credential, a token or an account id into a bug report or into this folder.

## Data hygiene: each flow deletes what it created

The last step of every flow deletes what the flow created, with the click below. The sweep `H1` in the [runner checklist](runner-checklist.md) then proves the account is empty.

| What a flow creates | Where it lives | How the runner deletes it |
|---|---|---|
| A conversation and its strategy | PathFinder and the account's VEuPathDB strategies | Sidebar row, `Conversation actions`, `Delete`, tick `Also delete strategy from <site name>`, `Delete`. Without the tick the row only moves to `Dismissed (<n>)`. |
| A dismissed conversation | PathFinder | Sidebar, `Dismissed (<n>)`, the row's `Delete permanently`, then `Delete permanently` in the dialog. |
| A saved strategy | PathFinder and VEuPathDB | Nav rail `Saved strategies`, the row's `Delete saved strategy`. There is no confirm; it deletes on VEuPathDB too. |
| A gene set | PathFinder | The gene set figure in the thread, `Delete`, then `Delete` in `Delete <name>?`. |
| A published dataset (VDI) | The account's workspace on the site | On the site: `Open dataset`, then the site's own delete. PathFinder never deletes a dataset (decided, see [known limits](known-limits.md)). |
| A memory | PathFinder | Settings, `Memory` tab, the row's `Delete <name>`, confirm the browser dialog. |
| A note | PathFinder, per conversation | Right rail `Notes`, `Delete note` on the card; the conversation delete removes the rest. |
| A control set, a scored run | PathFinder | Settings, `Data` tab, `Clear site data`, `Confirm`. |
| An EDA analysis | The account's analyses on the site | On the site: `Open in <Site>`, then the site's own delete. |
| A rating | PathFinder | Click the pressed `Good response` or `Bad response` again. |
