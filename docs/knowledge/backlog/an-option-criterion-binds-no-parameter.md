---
type: Backlog
---

# An option criterion binds no parameter

**What I did.** Asked, on plasmodb with the live model, which P. falciparum
genes are upregulated in gametocytes compared to asexual blood stages. FRAME
stated two criteria, one of them `gametocyte_timecourse_option`, a choice of
parameter option on the expression search rather than a search of its own.
BUILD pushed a three-step strategy of 3,128 genes.

**What I got.** `build_step_tree` reads the spec's structure, and the structure
does not name the option criterion, so no step and no parameter came from it.
The option the user asked for is in the spec and in the ledger, and nowhere in
the strategy WDK runs.

**Why that's wrong.** A criterion the researcher stated and FRAME recorded is
silently absent from the result. The count the user reads answers a broader
question than the one they asked, with nothing on screen saying so.

**Why it happens.** FRAME can record an option criterion, but nothing folds its
`resolved_params` into the step whose parameter it binds: `build_step_tree`
mints steps only for criteria the structure names, and an option criterion is
not a leaf.

**Fix.** Either FRAME folds an option criterion's value into the parameters of
the search criterion it qualifies at the time it binds (so the option is a
property of that criterion and never a criterion of its own), or BUILD applies
option criteria as parameter overrides on the step they qualify. A test builds
the incident spec and asserts the pushed step carries the option's parameter
value.

**What you'd get.** The three-step strategy runs the expression search with
the gametocyte timecourse option set, and the count answers the question asked.
