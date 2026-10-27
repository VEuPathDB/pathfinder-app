from __future__ import annotations

from pydantic_ai.tools import RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.gene_homes import SiteKind
from pathfinder.services.gene_sets.homes import site_kind

_ORTHOMCL = """\
## How this site's searches combine
Its record types are `group` (ortholog groups) and `sequence` (proteins, the genes a
request asks for). `GroupsByPhyleticPattern` returns groups, the `FromGroups` transform of
record type `sequence` turns them into proteins, and a `ByTaxonomy` step of record type
`sequence` intersected with those keeps one organism's proteins.
A count across a list of species is `GroupsByPhyleticPattern`: describe the groups to
`build_phyletic_expression(pattern)` with the codes `lookup_phyletic_codes` returns, and
bind `phyletic_expression` to the handle it returns; a compare past the expression caps
comes back with route `computed`, a snapshot whose `groups:` handle `set_criterion` takes
as `computed_groups`. A genus with no clade code is the list of its genome codes. A T
count counts genomes, and strains are genomes. When an expression names genomes of
several species or strains of one taxon, state the taxon's scope in `group_scopes`:
whole, with `except_codes` for the genomes the request leaves out, or named, exactly the
genomes the units write. `set_criterion` answers the expression in words with the size of
each list; when those words do not say what the request asks, correct the pattern and
build it again."""

_NOTES: dict[SiteKind, str] = {"orthomcl": _ORTHOMCL}


def pinned_site_notes(ctx: RunContext[AgentDeps]) -> str | None:
    return _NOTES.get(site_kind(ctx.deps.site_id))


__all__ = ["pinned_site_notes"]
