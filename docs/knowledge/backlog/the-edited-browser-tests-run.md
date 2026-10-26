---
type: Backlog
title: The edited browser tests run
description: Sixteen Playwright specs and fixtures were edited for the settings gear move and the appendix change without being run; run the e2e suite against a stack and fix what fails.
tags: [frontend, e2e]
generated: { by: claude-code/opus-5.5, at: 2026-10-26T00:00:00Z }
status: proposed
---

# The edited browser tests run

## What happens

Commits ebaa5374e and 839907a11 changed testids (settings-button, resultFigure, resultLine, evidence-enrichment-link) and removed the graph snapshot figure the specs used as a build signal.

## Done when

yarn test:e2e passes against a running stack.
