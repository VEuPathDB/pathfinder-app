"""The recorded OrthoMCL singleton turn: its spec, its taxonomy and its review."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    PhyleticTree,
    TaxonEntry,
)

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.named_taxa import NamedTaxon
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
)

QUESTION = (
    "Which Plasmodium species has the most singleton genes, meaning genes in a "
    "group of their own?"
)
ORGANISM = Constraint(
    kind=ConstraintKind.ORGANISM,
    requested_value="Plasmodium species",
    label="organism",
    source=ConstraintSource.USER_EXPLICIT,
)
SINGLETON = Constraint(
    kind=ConstraintKind.OTHER,
    requested_value="singleton genes, meaning genes in a group of their own",
    label="singleton ortholog groups",
    source=ConstraintSource.USER_EXPLICIT,
)
PLASMODIUM = NamedTaxon(name="Plasmodium", organisms=61)
GENOMES = (
    ("pfac", "Plasmodium falciparum CD01"),
    ("pfra", "Plasmodium fragile strain nilgiri"),
    ("pfsg", "Plasmodium falciparum 7G8 2019"),
    ("pfgb", "Plasmodium falciparum GB4"),
    ("pkno", "Plasmodium knowlesi strain H"),
    ("pblg", "Plasmodium blacklocki G01"),
    ("pyxn", "Plasmodium yoelii yoelii 17XNL"),
    ("pcyn", "Plasmodium cynomolgi strain B"),
    ("pber", "Plasmodium berghei ANKA"),
    ("pbbi", "Plasmodium brasilianum strain Bolivian I"),
    ("pfsn", "Plasmodium falciparum SN01"),
    ("pyoe", "Plasmodium yoelii yoelii 17X"),
    ("pyoy", "Plasmodium yoelii yoelii YM"),
    ("pfnf", "Plasmodium falciparum NF54"),
    ("powp", "Plasmodium ovale wallikeri PowCR01"),
    ("pfhb", "Plasmodium falciparum HB3"),
    ("preg", "Plasmodium reichenowi G01"),
    ("pknp", "Plasmodium knowlesi strain Malayan Strain Pk1 A"),
    ("pvpc", "Plasmodium vinckei petteri strain CR"),
    ("pvin", "Plasmodium vinckei vinckei strain vinckei"),
    ("pccb", "Plasmodium chabaudi chabaudi CB"),
    ("pvpw", "Plasmodium vivax PvW1"),
    ("pova", "Plasmodium ovale curtisi GH01"),
    ("pbil", "Plasmodium billcollinsi G01"),
    ("pfkt", "Plasmodium falciparum KH02"),
    ("pcha", "Plasmodium chabaudi chabaudi"),
    ("pviv", "Plasmodium vivax Sal-1"),
    ("pvld", "Plasmodium vinckei lentum DE"),
    ("pgab", "Plasmodium gaboni strain G01"),
    ("pyyx", "Plasmodium yoelii yoelii 17XNL 2023"),
    ("prel", "Plasmodium relictum SGS1-like"),
    ("pfsd", "Plasmodium falciparum SD01"),
    ("pvcr", "Plasmodium vinckei petteri CR 2020"),
    ("pfng", "Plasmodium falciparum NF166"),
    ("pmal", "Plasmodium malariae UG01"),
    ("pfkh", "Plasmodium falciparum KH01"),
    ("pfgn", "Plasmodium falciparum GN01"),
    ("pvip", "Plasmodium vivax P01"),
    ("pfad", "Plasmodium falciparum Dd2"),
    ("pinu", "Plasmodium inui San Antonio 1"),
    ("pfml", "Plasmodium falciparum ML01"),
    ("pvlk", "Plasmodium vivax-like Pvl01"),
    ("pvce", "Plasmodium vinckei Cameroon EL"),
    ("pvpv", "Plasmodium vivax PAM"),
    ("pvvc", "Plasmodium vinckei vinckei CY"),
    ("pfke", "Plasmodium falciparum KE01"),
    ("pvbd", "Plasmodium vinckei brucechwatti DA"),
    ("pfai", "Plasmodium falciparum IT"),
    ("pgas", "Plasmodium gaboni strain SY75"),
    ("pfal", "Plasmodium falciparum 3D7"),
    ("prei", "Plasmodium reichenowi CDC"),
    ("pkah", "Plasmodium knowlesi strain A1H1"),
    ("padl", "Plasmodium adleri G01"),
    ("pfnc", "Plasmodium falciparum NF135.C10"),
    ("pfag", "Plasmodium falciparum 7G8"),
    ("ppra", "Plasmodium praefalciparum strain G01"),
    ("pftg", "Plasmodium falciparum TG01"),
    ("pfga", "Plasmodium falciparum GA01"),
    ("pgal", "Plasmodium gallinaceum 8A"),
    ("pcym", "Plasmodium cynomolgi strain M"),
    ("pcoa", "Plasmodium coatneyi Hackeri"),
)
OTHER_GENOMES = (
    ("tgon", "Toxoplasma gondii ME49"),
    ("cpar", "Cryptosporidium parvum Iowa II"),
)


def taxonomy() -> PhyleticTree:
    root = TaxonEntry(id="ALL", parent_id=None, code="ALL", label="All", clade=True)
    clade = TaxonEntry(
        id="APIC", parent_id="ALL", code="APIC", label="Apicomplexa", clade=True
    )
    leaves = [
        TaxonEntry(id=code, parent_id="APIC", code=code, label=label, clade=False)
        for code, label in (*GENOMES, *OTHER_GENOMES)
    ]
    return PhyleticTree.from_taxa([root, clade, *leaves])


def taxon_pick(taxon: NamedTaxon | None) -> BoundValue:
    return BoundValue(
        value=MultiPickValue(values=[code for code, _ in GENOMES]),
        source="chosen",
        display_name="Taxon",
        taxon=taxon,
    )


def _criteria(taxon: NamedTaxon | None) -> list[Criterion]:
    return [
        Criterion(
            id="step_74948e37",
            text="ortholog groups containing exactly one protein total",
            search_name="GroupsBySequenceCount",
            record_class="group",
        ),
        Criterion(
            id="step_dc53498e",
            text="the proteins in the singleton ortholog groups",
            search_name="FromGroups",
            record_class="sequence",
            role="transform",
        ),
        Criterion(
            id="step_6d2035f5",
            text="all Plasmodium species represented in the database",
            search_name="ByTaxonomy",
            record_class="sequence",
            role="filter",
            resolved_params={"taxon_type_ahead": taxon_pick(taxon)},
        ),
    ]


def spec(taxon: NamedTaxon | None) -> OperationalSpec:
    return OperationalSpec(
        goal=QUESTION,
        constraints=[ORGANISM, SINGLETON],
        criteria=_criteria(taxon),
        structure=SpecStructure.model_validate(
            {
                "root": {
                    "kind": "combine",
                    "operator": "INTERSECT",
                    "inputs": [
                        {
                            "kind": "transform",
                            "criterionId": "step_dc53498e",
                            "inputs": [
                                {"kind": "leaf", "criterionId": "step_74948e37"}
                            ],
                        },
                        {"kind": "leaf", "criterionId": "step_6d2035f5"},
                    ],
                }
            }
        ),
    )
