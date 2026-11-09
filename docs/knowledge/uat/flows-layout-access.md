---
type: TestPlan
title: UAT flows - layout and access
description: The app at 1024 px and at a phone width, keyboard-only use of the composer and the cards, the dark colours a host page can turn on, and screen-reader names of the controls the flows use.
tags: [uat, flows, layout, accessibility, keyboard]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Layout and access (L)

Run once, on plasmodb, on a conversation that holds S2 and its evidence card. A side panel stays beside the conversation only while the conversation keeps 600 px; otherwise the one opened last floats over it as a drawer, and a floating panel closes on load, on navigation and on resize. The sidebar is 220 to 360 px.

## L1 - 1024 px wide - core, once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Browser window 1024 x 768 | Open the S2 conversation | No horizontal scroll of the page; the composer, `Send` and the usage pill visible |
| 2 | Panel toggle `Strategy` (top right of the conversation) | Open | The panel shows the root count and the 3 steps without clipping |
| 3 | Evidence card | Open the appendix below the reply, read `Evidence` | Every column of the step and requirement tables readable (wrapping allowed, no cut text) |
| 4 | Appendix | Read the closed line, then open it | The closed line reads `Appendix · <n> sections · <count> genes` and, with caveats, `<n> caveats`. Open, the sections read `A. Strategy`, `B. Evidence` and on, in two columns from three sections, one heading size and one text size in every section |
| 5 | Canvas | `Open` | Nodes, counts and the topbar fit; `Fit to view` fits the tree |

## L2 - Phone width - once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Browser 390 x 844 | Open the app | The sidebar and the right rail are collapsed; `Open conversation sidebar` opens the list |
| 2 | Conversation | Send `/help` | The slash menu fits the width |
| 3 | Evidence card, question card, proposal card | Read and answer | Each fits; buttons reachable without zooming; the open appendix is one column |

## L3 - Keyboard only - core, once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Do not touch the mouse | The composer input has focus on load |
| 2 | Composer | Type, Shift+Enter, type, Enter | A new line, then the message is sent |
| 3 | Composer | `/`, ArrowDown twice, Enter | The third command opens; Escape clears the input |
| 4 | N1 question card | Tab to an option, Space; Tab to `Next`, Enter; at the last question Tab to `Submit`, Enter | The answers are sent |
| 5 | S13 approval card | Tab to `Approve`, Enter | `Approved` |
| 6 | N7 proposal card | Tab into the comment box, type, Tab to `No`, Enter | `You said no.` |
| 7 | Settings | Open with the nav rail button; Tab through the tabs; Escape | Each tab is reachable and has a visible focus ring; Escape closes (the tabs are plain buttons, not a tab list) |
| 8 | Canvas | `r`, then `f` | Tidy layout, then fit to view |

## L4 - Dark mode - once

PathFinder has no dark-mode switch and does not follow the operating system; its dark colours apply when a host page that embeds it sets `data-theme="dark"` on the document (`apps/web/src/styles/globals.css`).

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The operating system in dark mode | Reload | The app stays light (by design; see [known limits](known-limits.md)) |
| 2 | Browser console | Run `document.documentElement.dataset.theme = "dark"` | Thread, cards, canvas and Settings turn dark without a reload; text stays readable |
| 3 | Same | Read the evidence card and the E3 volcano | `Nothing in the strategy answers it` and `No search on this site states it` readable in `Answered by`; volcano points and threshold lines visible |
| 4 | Sidebar, light | Read the active row | Readable (the e2e suite holds its contrast to 4.5:1 on four sites) |

## L5 - Screen-reader names - once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | A screen reader, the thread | Navigate | The thread is a `log`; buttons read `Send`, `Stop`, `Attach a gene-ID list, an image or a PDF`, `Good response`, `Bad response`, `Branch to a new conversation from here`, `Open Strategy`, `Open Review`, `Monthly spend <n>% of allowance` |
| 2 | Evidence card counts | Focus a count | `<n> positive controls recovered, click to copy the ids` |

## L6 - A shared conversation - once

Two browsers: the owner signed in, and a second browser signed out.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Owner, the conversation's top right | `Share` | Dialog `Share this conversation` with two boxes, both unticked, and `Create link` |
| 2 | Same | `Create link` | A `Link` and a `Password`, each with a copy button; `Copy it now. It is not shown again.` |
| 3 | Second browser | Open the link | A password form; the conversation's name is not shown |
| 4 | Same | Type the password, `Open` | The conversation under its name, marked `Read-only`; no composer, no Branch, Edit, rating or Build it |
| 5 | Owner | Send a message | Second browser: `The conversation is answering. The reply shows here when it is done.`, then the reply within a few seconds of the owner seeing it end |
| 6 | Owner | Tick `Anyone with the link can open it` | The password lines go away; a fresh second browser opens the link with no password |
| 7 | Owner | Tick `Let people copy it into their own account` | A signed-out viewer sees `Sign in to make a copy`; a signed-in viewer sees `Make a copy`, which opens `<name> (copy)` in their own list |
| 8 | Owner, in a conversation that listed its control sets | Tick `Include what it read from your account` | The viewer's reload shows the list; unticked, the call shows `Not shared: this read the owner's account.` |
| 9 | Owner | `Stop sharing` | The link answers `This link is no longer shared.` |
