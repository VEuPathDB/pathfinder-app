---
type: Backlog
---

# Experiments across sites, and the orthology transform

Release a16. Two underused levers. The semantic index covers one site's searches;
a Plasmodium question cannot learn that CryptoDB holds an experiment on the same
life-cycle stage. And orthology, the transform that carries a gene set from one
organism to another, is a WDK step PathFinder can already build but rarely
chooses.

Measured on plasmodb (v0.2.0a12, conversation e9f2a030 on cedar, 2026-09-23): the
request "keep only those with syntenic orthologs in Plasmodium vivax P01" was
bound to the Orthology Phylogenetic Profile search (genes whose profile includes
P. vivax, 4,889 genes, intersect to 73) and the reply called it "the site's
search realization of the requested syntenic-ortholog criterion". The researcher
had to ask for the orthology transform. The transform then answered 67 P. vivax
records, which are the orthologs, not the P. falciparum genes that have one; the
request wanted the latter, which is the transform applied twice (to P. vivax and
back) or the profile search with the syntenic option where the site offers it.

## What

1. Cross-site experiment and study metadata in the index, answered as a ranked
   short list (site, organism, assay, condition, one line each) so the model asks
   for one study's detail instead of reading fourteen catalogs.
2. The lane rule the researcher set: the current site's own hits are ranked
   exactly as they are today, and a few hits from other sites are appended as
   diversity, each labelled with its site. A hit from another site is never bound
   as a criterion on this site; it can inform a criterion (a condition name, a
   gene list carried over by orthology) and nothing else. The model is told in
   the tool result which entries are its own site's and which are not.
3. Orthology as a first-class move: a request that says "orthologs in X",
   "conserved in X", "with a syntenic ortholog in X" or "carry this to X" reaches
   the transform family (and the double transform when the result must stay in
   the source organism), with the profile search offered only when the request
   asks for a profile. `syntenic` is a parameter of the transform, not a word
   FRAME drops.

## Constraints

The context budget: the cross-site list is capped and one line per entry; detail
is a second call. The record type after a transform is the target organism's,
and the reply must say so (the a12 reply did; the choice before it was wrong).
Regression tests: the measured request binds the transform, not the profile; a
cross-site hit carries its site and cannot be bound; the ranked list keeps the
own-site order unchanged with the extra entries after it.
