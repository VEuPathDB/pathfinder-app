"""The canned specs whose values the site sets: a domain step whose free-text
half holds the radio-off value beside a profile that excludes a species the
message names by its label, and a text step that shares its organism with a
step that binds no text."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import CriterionSpec, SpecPlan, combine, leaf
from pathfinder.ai.models.mock.strategy_specs import signal_peptide

INTERPRO = "GenesByInterproDomain"
ORTHOLOG_PATTERN = "GenesByOrthologPattern"
TEXT = "GenesByText"
# Two Pfam families only Plasmodium genomes annotate.
DOMAINS = ("PF09717", "PF18680")
# The clade tree code of the human reference proteome.
HUMAN = "hsap"


def radio_off_domain_spec(values: SiteValues) -> SpecPlan:
    """The domain step, its free-text half left null, INTERSECT a profile that
    excludes the human reference proteome."""
    domain = CriterionSpec(
        criterion_id="specific_domain",
        text=f"{values.organism} genes with a domain only its genus carries",
        search_name=INTERPRO,
        values={
            "organism": [values.organism],
            "domain_database": "Pfam",
            "domain_typeahead": list(DOMAINS),
            "domain_accession": None,
        },
    )
    profile = CriterionSpec(
        criterion_id="no_human_ortholog",
        text="genes with no ortholog in Homo sapiens",
        search_name=ORTHOLOG_PATTERN,
        values={
            "organism": [values.organism],
            "excluded_species": [HUMAN],
            "included_species": None,
        },
    )
    return SpecPlan(
        title=f"{values.organism} genus-specific domain genes without a human ortholog",
        criteria=(domain, profile),
        structure=combine(CombineOp.INTERSECT, leaf(domain), leaf(profile)),
    )


def text_beside_organism_spec(values: SiteValues) -> SpecPlan:
    """A product text step UNION the signal peptide step, both on the site
    organism."""
    text = CriterionSpec(
        criterion_id="gpi_text",
        text=f"{values.organism} genes whose product names a GPI anchor",
        search_name=TEXT,
        values={
            "text_search_organism": [values.organism],
            "text_expression": "GPI anchor",
            "text_fields": ["product"],
        },
    )
    peptide = signal_peptide(values)
    return SpecPlan(
        title=f"{values.organism} GPI anchor or signal peptide genes",
        criteria=(text, peptide),
        structure=combine(CombineOp.UNION, leaf(text), leaf(peptide)),
    )


__all__ = [
    "DOMAINS",
    "HUMAN",
    "INTERPRO",
    "ORTHOLOG_PATTERN",
    "TEXT",
    "radio_off_domain_spec",
    "text_beside_organism_spec",
]
