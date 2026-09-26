"""The canned specs the build arcs frame, each on the values of its own site.

A search the site's seeds run carries the values the seed ran it with; a
search no seed runs falls back to the site's own organism search.
"""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.models.mock.site_values import ParamValues, SiteValues
from pathfinder.ai.models.mock.specs import CriterionSpec, SpecPlan, combine, leaf

TAXON = "GenesByTaxon"
SIGNAL_PEPTIDE = "GenesWithSignalPeptide"
TM_DOMAINS = "GenesByTransmembraneDomains"
ORTHOLOGS = "GenesByOrthologs"
GO_TERM = "GenesByGoTerm"

# The transmembrane ranges the standard flows state.
TM_RANGE = ("2", "99")
ZERO_TM_RANGE = ("99", "99")
RELAXED_MIN_TM = "15"
EDITED_MIN_TM = "1"


def seed_criterion(
    values: SiteValues,
    search_name: str,
    criterion_id: str,
    text: str,
    *,
    role: str = "filter",
    overrides: ParamValues | None = None,
) -> CriterionSpec:
    """A criterion on the values a seed ran ``search_name`` with, or on the
    site organism alone when no seed runs it."""
    seed = values.leaf(search_name)
    held = {"organism": [values.organism]} if seed is None else seed.values
    return CriterionSpec(
        criterion_id=criterion_id,
        text=text,
        search_name=search_name,
        role=role,
        values={**held, **(overrides or {})},
    )


def signal_peptide(
    values: SiteValues, criterion_id: str = "signal_peptide"
) -> CriterionSpec:
    return seed_criterion(
        values,
        SIGNAL_PEPTIDE,
        criterion_id,
        f"{values.organism} genes with a predicted signal peptide",
        role="seed",
    )


def tm_domains(values: SiteValues, low: str, high: str) -> CriterionSpec:
    return seed_criterion(
        values,
        TM_DOMAINS,
        "tm_domains",
        f"{values.organism} genes with {low} to {high} transmembrane domains",
        overrides={"min_tm": low, "max_tm": high},
    )


def _one(title: str, crit: CriterionSpec) -> SpecPlan:
    return SpecPlan(title=title, criteria=(crit,), structure=leaf(crit))


def _two(
    title: str, operator: CombineOp, left: CriterionSpec, right: CriterionSpec
) -> SpecPlan:
    return SpecPlan(
        title=title,
        criteria=(left, right),
        structure=combine(operator, leaf(left), leaf(right)),
    )


def single_spec(values: SiteValues) -> SpecPlan:
    return _one(
        f"{values.organism} signal peptide genes (mock)", signal_peptide(values)
    )


def intersect_spec(values: SiteValues) -> SpecPlan:
    return _two(
        f"{values.organism} secreted membrane genes (mock)",
        CombineOp.INTERSECT,
        signal_peptide(values),
        tm_domains(values, *TM_RANGE),
    )


def union_spec(values: SiteValues) -> SpecPlan:
    return _two(
        f"{values.organism} signal peptide or membrane genes (mock)",
        CombineOp.UNION,
        signal_peptide(values),
        tm_domains(values, *TM_RANGE),
    )


def minus_spec(values: SiteValues) -> SpecPlan:
    return _two(
        f"{values.organism} signal peptide genes without membrane domains (mock)",
        CombineOp.MINUS,
        signal_peptide(values),
        tm_domains(values, *TM_RANGE),
    )


def zero_spec(values: SiteValues) -> SpecPlan:
    return _one(
        f"{values.organism} many-domain genes (mock)",
        tm_domains(values, *ZERO_TM_RANGE),
    )


def _go(values: SiteValues) -> CriterionSpec:
    """The seed's GO term, else the first term the sheet lists. The free-text
    half stays null: a proposal that fills both ORed halves is refused."""
    text = f"{values.organism} genes by GO term"
    if values.leaf(GO_TERM) is None:
        return CriterionSpec(
            criterion_id="go_genes",
            text=text,
            search_name=GO_TERM,
            values={"organism": [values.organism], "go_term": None},
            sheet_first="go_typeahead",
        )
    return seed_criterion(
        values, GO_TERM, "go_genes", text, overrides={"go_term": None}
    )


def go_spec(values: SiteValues) -> SpecPlan:
    return _one(f"{values.organism} genes by GO term (mock)", _go(values))


def count_spec(values: SiteValues) -> SpecPlan:
    crit = CriterionSpec(
        criterion_id="gene_type",
        text=f"protein-coding genes of {values.organism}",
        search_name="GenesByGeneType",
        role="seed",
        values={"organism": [values.organism]},
    )
    return _one(f"{values.organism} protein-coding genes (mock)", crit)


def combined_spec(values: SiteValues) -> SpecPlan:
    """Five nodes over three search types: (text UNION go) INTERSECT taxon."""
    text = seed_criterion(
        values, "GenesByText", "text_genes", f"{values.organism} genes by product text"
    )
    go = _go(values)
    taxon = CriterionSpec(
        criterion_id="taxon_genes",
        text=f"{values.organism} genes",
        search_name=TAXON,
        role="seed",
        values={"organism": [values.organism]},
    )
    return SpecPlan(
        title=f"{values.organism} comprehensive strategy (mock)",
        criteria=(text, go, taxon),
        structure=combine(
            CombineOp.INTERSECT,
            combine(CombineOp.UNION, leaf(text), leaf(go)),
            leaf(taxon),
        ),
    )


def cross_organism_spec(values: SiteValues) -> SpecPlan:
    """The same search on two organisms under an INTERSECT, which never runs."""
    here = signal_peptide(values)
    there = CriterionSpec(
        criterion_id="signal_peptide_elsewhere",
        text="genes of a second organism with a predicted signal peptide",
        search_name=here.search_name,
        role="seed",
        values=dict(here.values),
        alt_param="organism",
        site_organism=values.organism,
    )
    return _two(
        f"{values.organism} and a second organism (mock)",
        CombineOp.INTERSECT,
        here,
        there,
    )
