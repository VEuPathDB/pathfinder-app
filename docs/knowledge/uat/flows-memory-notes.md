---
type: TestPlan
title: UAT flows - memory and notes
description: A liked and a disliked answer and what they change later, the recalled-memories figure, the notes the assistant keeps in the rail, the Memory settings tab with its edit, delete and tombstone, and a preference remembered across conversations.
tags: [uat, flows, memory, notes, ratings]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Memory and notes (M)

Notes belong to one conversation; memories reach every conversation of the account. Start from a clean account ([sites and accounts](sites-and-accounts.md)): the dev account used for the measurements recalls 12 memories on every turn, four of them the same preference, and that noise is exactly what these flows must not inherit.

## M1 - Like an answer - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S2 conversation, the build reply | Hover, `Good response` | The button shows pressed; after a reload it still is |
| 2 | Settings, `Memory`, `Cases` | Open | A case named for the S2 goal ("... signal peptide and ... transmembrane domains"), summary "reached 116 results through (GenesWithSignalPeptide INTERSECT GenesByTransmembraneDomains)", tag `pinned` |
| 3 | New conversation | Send the S2 prompt again | `Recalled memories` lists that case; the build reaches 116 genes |
| 4 | The first conversation | Click `Good response` again | The rating clears; the `pinned` tag goes |

## M2 - Dislike an answer - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S3 conversation (UNION), the build reply | Hover, `Bad response` | Pressed; survives a reload |
| 2 | Settings, `Memory`, `Cases` | Open | The case of that answer is gone |
| 3 | New conversation | Send the S3 prompt again | `Recalled memories` does not list the disliked case |
| 4 | Composer | Rate while offline (see L5) | Toast `The rating was not saved.` |

## M3 - The recalled-memories figure - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Any turn after M1 and N11 | Read the figure above the reply | Title `Recalled memories`, caption `<n> memories`; each row a kind badge (`Gene set`, `Strategy`, `Preference`, `Knowledge`, `Case`) and a name |
| 2 | A long name | Hover | The name is cut with an ellipsis on screen; the full name shows as a tooltip |
| 3 | Two memories with one name | Read | Each carries its date and time |
| 4 | A `Strategy` row | Click | Its source conversation opens |
| 5 | A `Preference` row | Click | Settings opens on `Memory` with that row highlighted |

## M4 - Notes in the rail - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S2 conversation | Right rail `Notes` | Section `PINNED` (CSS) with a note titled like "Signal peptide and transmembrane intersection" (the build pins it: trace rows `Save note`, `Pin note`) |
| 2 | The note card | Click | The body opens |
| 3 | The note card | `Unpin` | It moves to `RECENT` (CSS) |
| 4 | The note card | `Delete note` | It is gone at once; no confirm; a new conversation shows `No notes yet. The assistant saves findings here as it works.` |

Measured: every S2 build saved and pinned one note ("Note saved: Signal peptide and transmembrane intersection").

## M5 - The Memory settings tab: edit, delete, tombstone - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Nav rail `Settings`, tab `Memory` | Open | `Search memories...`; sections `Gene sets`, `Strategies`, `Preferences`, `Knowledge`, `Cases`, each with a count, collapsed |
| 2 | `Search memories...` | Type `gametocyte` | The N11 preference; an unmatched word reads `No memories matched "<word>".` |
| 3 | The row | Click | Dialog `Edit memory`: `Name`, `Summary`, `Tags (comma-separated)`, `Content (JSON)`, `Auto-retrieve in future conversations`; `Cancel` / `Save` |
| 4 | Dialog | Change the summary to `UAT edited summary`, `Save` | The row shows the new summary; the next turn's recall uses it |
| 5 | `Content (JSON)` | Enter `[1]` | `Invalid JSON - must be an object.`; `Save` disabled |
| 6 | A `Cases` row (from S2) | `Delete <name>` | Browser confirm `Delete "<name>"? PathFinder will not save it again on its own.`; OK removes it |
| 7 | New conversation | Send the S2 prompt again and wait for `Supported` | The deleted case is not written back: the `Cases` count is unchanged |

## M6 - A preference remembered across conversations - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | After N11, a new conversation | Send `Which dataset do I prefer for gametocyte expression?` | `Recalled memories` lists the preference; the reply names the Su et al. strand-specific dataset; nothing is built |
| 2 | Account B | Send the same | B's reply does not know the preference |

Measured: "You prefer the **Su et al. strand-specific RNA-seq dataset** for *Plasmodium falciparum* 3D7 gametocyte-expression analyses." 14 s, $0.010.
