---
type: Decision
title: A held expression is compared by its parsed form
description: The value a step holds and the value the site holds for phyletic_expression are one value when their parsed forms are equal, so redundant parentheses are no difference and a regrouping is. Exact strings, the graded normal form, the site's reading and a new parameter value type were rejected.
tags: [verification, orthomcl, wdk-alignment]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# The rule

`expression_handles.same_wire_value` compares two wire values of one parameter. Equal strings are
the same value. Two strings of `phyletic_expression` are the same value when
`PhyleticExpression.parse` gives equal forms for both. A value that does not parse equals only
itself. Every other parameter compares as written.

`site_changes._differing` uses it, so the `bound_values` check and the read of the site's edits
share the rule.

# Why the two strings differ

`validate_parameters` holds an expression in `PhyleticExpression.render`, which writes each nested
term in parentheses. A build sends that form, and the step keeps the form it was bound with. The
site stores what it receives, in either spelling.

# Rejected

**Exact strings.** Every expression of an OR of AND terms that the builder writes then reads as
moved: the check fails and the graph takes the site's spelling as an edit.

**Removing parentheses from the strings.** `a AND (b OR c)` and `a AND b OR c` are different parsed
forms, and removing them makes the two one string. A value that states a regrouping must stay a
difference.

**The graded normal form (`evals.expressions.meaning`) or `site_reading`.** Both read the expression
as the site runs it, so a regrouping compares equal. The normal form also needs the taxonomy and
treats a clade and its genome list as one unit. This check asks whether the site holds the value that
was bound, not whether two values select the same groups. Term order stays a difference for the same
reason.

**A parameter value type for expressions.** WDK types `phyletic_expression` as a string parameter, and
`StringValue` does not know its name. A new member of the `ParamValue` union adds a discriminant WDK
does not have, for a comparison with one caller.
