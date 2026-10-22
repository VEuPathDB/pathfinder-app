---
type: Backlog
title: A mention of Settings opens Settings
description: The first-run notice says "Change the models and tiers in Settings -> Model" and the help pages name Settings tabs in plain text, while the only way in is the gear at the bottom of the nav rail; each mention becomes a link that opens Settings on the named tab, and the gear moves beside Help.
tags: [frontend, settings, first-run, help]
generated: { by: claude-code/opus-5, at: 2026-10-20T00:00:00Z }
status: proposed
---

# A mention of Settings opens Settings

## What happens

The default-provider notice on the empty conversation says "Change the models and
tiers in Settings -> Model". `features/help/HelpPage.tsx` and
`features/help/YourDataPage.tsx` name Settings tabs (Model, Provider keys, Privacy,
Memory) in plain text. Settings opens only from the gear at the bottom of the left
nav rail, while Help sits at the bottom right. On the PlasmoDB and EuPathDB
development sites the gear was also cut off at the window's bottom edge, because
their web-monorepo checkouts predate the PathFinder page layout fix (web-monorepo
#1918 and #1919); a pull and rebuild of those sites fixes that part.

## Change

1. Each mention of a Settings tab is a link that opens Settings on that tab.
2. The Settings gear sits beside Help at the bottom right, so both are in one corner.

## Done when

Clicking "Settings -> Model" in the notice opens Settings on the Model tab, the help
pages' mentions do the same for their tabs, and a test covers the notice link.
