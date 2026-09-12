---
type: Backlog
---

# A parameter-heavy search cannot fit the FRAME ceiling

**What I did.** On plasmodb, a five-criterion request (text protease OR GO protease, gametocyte RNA-seq, P. vivax orthologs, non-synonymous SNPs) was framed by FRAME under `phase_usage_limits(5)` (`ai/lead/sub_agent_tools.py`: 5 criteria times the per-criterion allowance plus the structure calls = 58 tool calls). On the portal, a sixteen-step drug-target request framed under a 64-call ceiling.

**What I got.** plasmodb: 5 sheets opened, then 31 `get_parameter_options` calls (12 of them for `GenesByNgsSnps`, which has 12 open parameters), and `sub-agent hit its usage ceiling ... tool_calls_limit of 58 (tool_calls=63)` before any criterion was bound; the Lead asked the user to narrow. Portal: one criterion bound at the ceiling. The reply was honest in both cases, and the user got no strategy.

**Why that's wrong.** The requests the product is meant for (7+ steps, several evidence lines) cannot be framed in one turn because the protocol charges one tool call per vocabulary parameter and the ceiling assumes about ten calls per criterion.

**Why it happens.** `set_criterion`'s sheet lists a parameter's name and type but not its vocabulary, so the model reads each vocabulary with `get_parameter_options`; the ceiling is sized by criterion count, not by the parameters the chosen searches expose.

**Fix.** The sheet carries a vocabulary inline when it is small (at most a few dozen entries), so a bind needs no option read for it; and the ceiling grows with the open parameters the sheets expose, bounded by the phase maximum. Red first: a sheet for a search with a small vocabulary shows it; a sheet with 12 parameters raises the ceiling.

**What you'd get.** The five-criterion request binds within one pass; the SNP search costs one sheet read and one bind.
