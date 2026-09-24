---
type: Backlog
---

# A gene-id distribution is recorded, not typed

`services/eda/gene_subset.py::gene_count` reads the distinct count of the gene-id
variable's distribution on the gene entity, so a subset's gene count is a count of
genes and not of the entity's per-sample rows. The tests that pin the numbers
(842 of 5,720 genes under a sense-count filter, 5,595 of 5,803 on the phenotype
study) hold values read live from plasmodb, typed into
`tests/_support/eda_wire.py::_GENE_ID_STATISTICS`, the distribution bodies the
wire double answers, and `tests/_support/eda_step_doubles.py`
(`PHENOTYPE_GENES`, `DE_GENES`), the counts the step tests expect.

Every other EDA body the suite reads is a recorded fixture under
`veupathdb.testing.fixtures/eda/` in `veupathdb-py`, verified against the site by
`python -m veupathdb.devtools.fixtures verify`. Record the gene-id distribution
bodies there (the unfiltered entity and one filtered subset per study the suite
uses), take the client release that ships them, and read the numbers from the
fixture in both modules.
