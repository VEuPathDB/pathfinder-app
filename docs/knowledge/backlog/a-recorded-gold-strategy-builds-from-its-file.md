---
type: Backlog
title: A recorded gold strategy builds from its file
description: None of the recorded gold strategy files validates as a StrategyStepNode, because their parameter values are raw wire strings, so POST /api/v1/eval/build-gold builds none of them.
tags: [eval, gold, wire]
status: proposed
---

# What is wrong

Every file under `thesis/eval/gold_strategies/` stores each step's parameters as the strings
WDK sends. `StrategyStepNode.model_validate` takes typed parameter values, so
`build_gold_strategy` refuses each file before it reads the tree.

# What changes

The build route reads a gold tree in its wire shape and types each parameter against the
search's own parameter sheet, the same parse a strategy read back from the site takes;
or the files are rewritten in the typed shape once, by that same parse.

# How it is checked

A test builds each recorded gold file through the route against the recorded catalog, with
no step posted for a tree the site would refuse.
