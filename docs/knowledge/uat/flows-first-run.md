---
type: TestPlan
title: UAT flows - first run and navigation
description: Sign-in, the site menu, a site that is down, the conversation list, a new conversation, rename, delete, branch, revert, reload in the middle of a turn, closing the tab during a background task, and two accounts kept apart.
tags: [uat, flows, navigation, conversations, isolation]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# First run and navigation (F)

Run on each site in [sites and accounts](sites-and-accounts.md) unless the flow says one site. Labels are the app's own, as the code renders them; `(CSS)` marks text the stylesheet upper-cases on screen.

## F1 - Sign in - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Browser, profile of account A, signed out | Open `<pathfinder-url>` | The app is replaced by one dialog: `PathFinder`, `VEuPathDB Strategy Builder` (CSS), `Sign in with your VEuPathDB account to build and manage search strategies.`, fields `Email` and `Password`, button `Sign in`, line `We do not store your login credentials.` No close button; Escape does nothing. |
| 2 | Sign-in dialog | Enter account A's email and a wrong password, `Sign in` | `Login failed. Please check your credentials.` The dialog stays. |
| 3 | Sign-in dialog | Enter the right password, `Sign in` | Button reads `Signing in...`, then the dialog closes and the URL is `/<site>/conversation`; the entry site is the portal when it answers. |
| 4 | First signed-in visit | Read the notice | Dialog `How PathFinder learns`, buttons `Turn off` and `OK`. Click `OK`. It does not appear again after a reload. |
| 5 | Top bar | Read | `Logged in as <account name>`, `Log out`; the quota pill `$<used> / $<limit>` with tooltip `Account total this month, across all conversations.` |
| 6 | Top bar | `Log out`, then sign in again | Back to step 1's dialog; after sign-in the conversation list is unchanged. |

## F2 - Site menu - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Nav rail | Hover the site icon | Tooltip `Switch site`. |
| 2 | Nav rail, `Switch site` | Click | Menu with `COMPONENT SITES` (CSS) and `PORTAL` (CSS) groups; items read `PlasmoDB (Plasmodium)`, `VectorBase (Vectors)`, `ToxoDB (Toxoplasma)`, `FungiDB (Fungi)`, `VEuPathDB Portal (All organisms)`. No item carries `Couldn't reach`. |
| 3 | Site menu | Pick `ToxoDB (Toxoplasma)` | URL `/toxodb/conversation`; the top bar banner changes; the conversation list shows only toxodb conversations. |
| 4 | Site menu | Pick the site you started on | The list returns to that site's conversations. |

## F3 - A site that is down

Needs the deployment operator (see `R1` in [resilience flows](flows-resilience.md)); do it once, on one site.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Operator | Make one site's catalog fail to load (R1, step 1) | `GET /api/v1/sites` answers that site with `available: false` and an `unavailableReason`. |
| 2 | Nav rail | Open `Switch site` | The site's item reads `Couldn't reach` with a warning glyph. |
| 3 | Site menu | Pick that site | The rail, the sidebar and the top bar stay; the content area shows `Couldn't reach <site name>` and `PathFinder cannot use this site right now: <reason>. It keeps trying every minute, so this may clear on its own.`, then `Try another site:` and one link per site that answers. The rail's site icon carries the warning glyph, tooltip `Couldn't reach <site name>`. |
| 4 | Operator | Restore the site | Within 60 s, without a reload, the marker and the notice go away. |

`CLAUDE.md` calls this marker "Not responding"; the code renders `Couldn't reach`. Test `Couldn't reach`.

## F4 - The conversation list - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Sidebar, after any S flow | Read the rows | Header `Conversations` (CSS). Each row: the title, then `<n> steps` when the strategy has steps, then the time (`2:34 PM`, `Yesterday`, `Feb 14`). |
| 2 | Sidebar, `Search conversations...` | Type two letters of one title | Only the rows whose title holds them stay; an unmatched text reads `No conversations match your search.` |
| 3 | Sidebar | `Refresh conversations` | The rows reload; the order is newest activity first. |

## F5 - New conversation and the assistant menu - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Sidebar | `New conversation` (pencil) | URL `/<site>/conversation`; greeting (`Good morning` / `Good afternoon` / `Good evening` / `Still up?`), blurb `Build and refine multi-step <Site> search strategies with guided parameter selection and validation.`, four suggestion cards. |
| 2 | Sidebar | `Choose an assistant` (chevron) | Menu `NEW CONVERSATION WITH` (CSS): `Strategy builder`, `Site help`, `Open a VEuPathDB strategy...`. |
| 3 | Assistant menu | `Site help` | URL ends `?assistant=site_help`; chip `Site help`; blurb `Find your way around the VEuPathDB sites: which site covers an organism, and what each one lets you search.` No suggestion cards. |
| 4 | Composer | Send `Which site holds Aedes aegypti?` | A reply naming VectorBase; the new sidebar row's meta line starts `Site help`. |
| 5 | Settings, `Model` tab | Read | The intro names `Site help`, one stage row `Site help`. |
| 6 | Cleanup | Delete the conversation (F7) | - |

## F6 - Rename - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Sidebar row | Hover, `Conversation actions`, `Rename` | An inline input holding the title. |
| 2 | Inline input | Type `UAT rename F6`, Enter | The row reads `UAT rename F6`; after a reload it still does. |
| 3 | Composer | Type `/rename`, pick it, enter `UAT rename F6 slash`, `Next` | Toast `Renamed to "UAT rename F6 slash".`; the row updates. |
| 4 | Composer | `/rename` with an empty name | Toast `Name cannot be empty.` |
| 5 | The S2 conversation, composer | Send `Rename this strategy to UAT signal peptide screen.` | Trace row `Rename strategy`; caption `UAT signal peptide screen - 116 genes`; the sidebar row, the canvas topbar and the strategy on the site all read the new name. Not measured |

## F7 - Delete, dismiss and restore - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Sidebar row of a conversation with a strategy | `Conversation actions`, `Delete` | Dialog `Delete conversation`, body `Delete "<title>"? It moves to Recently deleted and can be restored later.`, checkbox `Also delete strategy from <site name>` unticked, note `PathFinder created this strategy in <site name>. Deleting it is permanent, and the conversation will not be recoverable.` |
| 2 | Dialog | Leave the box unticked, `Delete` | The row leaves the list; `Dismissed (1)` appears. The strategy is still on the site. |
| 3 | Sidebar | Open `Dismissed (1)`, `Restore conversation` | The row is back with its messages. |
| 4 | Sidebar row | `Delete`, tick `Also delete strategy from <site name>`, `Delete` | The row is gone and not under `Dismissed`; on the site the strategy is gone. |

The dialog says "Recently deleted"; the section is named `Dismissed`. Record it as a minor if it is still so.

## F8 - Branch - core on plasmodb

Uses the conversation of `S4` then `S9` in [standard strategy flows](flows-strategy-standard.md) (two turns: MINUS 363 genes, then 191 genes).

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Thread, first assistant reply | Hover, `Branch to a new conversation from here` | A new conversation opens, nested under the source row with a branch icon. |
| 2 | Branch | Read | It holds exactly the first user message and the first reply. The Strategy panel shows the first turn's tree, `3 steps`, 363 genes, under a strategy id of its own (the evidence card link differs from the source's). |
| 3 | Branch, composer | Send `How many genes does this strategy return?` | The reply says 363, not 191. |
| 4 | Source conversation | Reopen it | Unchanged: both turns, 191 genes. |
| 5 | Cleanup | Delete the branch with `Delete branch` under the source row, ticking the strategy box | - |

## F9 - Revert - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S4 + S9 conversation, first user message | Hover, `Edit`, send the same S4 text again, `Save...` | Dialog `Edit earlier message`: `Branch to a new conversation` and `Revert this conversation`, with the text `Delete every message after this point in this conversation. Notes and pending tasks from those turns are also removed. The strategy goes back to what it was at this message; a later version stays in your VEuPathDB account. Saved gene sets are kept.` |
| 2 | Dialog | `Revert` | Every message after the edited one is gone; a new turn runs the edited text. |
| 3 | Thread | Wait | The strategy is the S4 tree again, 363 genes; `Notes` holds no note of the deleted turns. |
| 4 | Browser | Reload | The deleted turns stay gone. |

## F10 - Reload and Stop in the middle of a turn - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send the S2 prompt | Status line `Planning...`. |
| 2 | Browser | Reload while `Planning...` shows | The thread reopens on the same URL and keeps streaming the same turn; no text says "reconnecting". The turn ends with the S2 result (116 genes). |
| 3 | New conversation | Send the S2 prompt, then `Stop` while `Planning...` shows | `You stopped this response.`; the trace group reads `Stopped`; `Send` is back. |
| 4 | Same conversation | Send `Continue.` | A normal turn runs; no error card. |

## F11 - Close the tab during a background task - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send the E2 prompt of [EDA flows](flows-eda.md) | A task row `Run differential expression` with `~120 s` and a percent. |
| 2 | Browser | Close the tab while the percent is under 100 | - |
| 3 | Browser, 3 minutes later | Open `<pathfinder-url>`, open the conversation | The task row reads its summary (not a percent), the reply is there (201 genes), and the right rail `Tasks` panel lists `Run differential expression` with status `complete`. |

## F12 - Two accounts stay apart - core, once

Account A in one browser profile, account B in another (see [sites and accounts](sites-and-accounts.md)).

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Account A | Run S2 on plasmodb, save a gene set (G1), remember a preference (M6), note the conversation URL | - |
| 2 | Account B, plasmodb | Read the sidebar | None of A's conversations. |
| 3 | Account B | Open A's conversation URL | Redirect to `/plasmodb/conversation`; none of A's messages are shown. |
| 4 | Account B | Settings, `Memory` | None of A's memories; `Recalled memories` in B's next turn names none of them. |
| 5 | Account B | `/export`, `Latest gene set on this site (CSV)` | `No gene sets to export.` (or B's own set only). |
| 6 | Account B | EDA tab, `Your datasets` | None of A's uploads. |
| 7 | Account B | Nav rail `Saved strategies` | None of A's saved strategies. |

| 8 | Account A's profile | On plasmodb.org sign out and sign in as account B, then return to PathFinder and send a message | PathFinder relinks or shows `Signed in to VEuPathDB as a different account than this PathFinder session. Sign in again.`; it never acts on B's VEuPathDB account under A's PathFinder session |

Any of A's data shown to B is a blocker (privacy breach).
