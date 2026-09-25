---
type: TestPlan
title: UAT flows - layout and access
description: The app at 1024 px and at a phone width, keyboard-only use of the composer and the cards, the dark colours a host page can turn on, and screen-reader names of the controls the flows use.
tags: [uat, flows, layout, accessibility, keyboard]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Layout and access (L)

Run once, on plasmodb, on a conversation that holds S2 and its evidence card. Below 900 px the sidebar and the right rail collapse on load and on each resize; the sidebar is 220 to 360 px and the main column keeps at least 520 px.

## L1 - 1024 px wide - core, once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Browser window 1024 x 768 | Open the S2 conversation | No horizontal scroll of the page; the composer, `Send` and the usage pill visible |
| 2 | Right rail `Strategy` | Open | The panel shows the 3 steps and the footer `3 steps` without clipping |
| 3 | Evidence card | Read | Every column of the step and requirement tables readable (wrapping allowed, no cut text) |
| 4 | Canvas | `Open` | Nodes, counts and the topbar fit; `Fit to view` fits the tree |

## L2 - Phone width - once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Browser 390 x 844 | Open the app | The sidebar and the right rail are collapsed; `Open conversation sidebar` opens the list |
| 2 | Conversation | Send `/help` | The slash menu fits the width |
| 3 | Evidence card, question card, proposal card | Read and answer | Each fits; buttons reachable without zooming |

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
| 3 | Same | Read the evidence card and the E3 volcano | `Not met` (red) and `No search states it` (amber) distinguishable; volcano points and threshold lines visible |
| 4 | Sidebar, light | Read the active row | Readable (the e2e suite holds its contrast to 4.5:1 on four sites) |

## L5 - Screen-reader names - once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | A screen reader, the thread | Navigate | The thread is a `log`; buttons read `Send`, `Stop`, `Attach a gene-ID list, an image or a PDF`, `Good response`, `Bad response`, `Branch to a new conversation from here`, `Open Strategy`, `Open Notes` |
| 2 | Evidence card counts | Focus a count | `<n> positive controls recovered, click to copy the ids` |
