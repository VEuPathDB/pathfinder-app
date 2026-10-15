"""A saved set shows on its own site, on every site that holds one of its genes,
on the portal and on OrthoMCL, each time with the ids that site reads."""

from __future__ import annotations

import pytest

from pathfinder.domain.gene_homes import GeneHome, SiteKind, genes_on

_PLASMO = {
    "PF3D7_0103400": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb"),
    "PF3D7_0110100": GeneHome(gene_id="PF3D7_0110100", site_id="plasmodb"),
}
_PORTAL = {
    **_PLASMO,
    "TGME49_200250": GeneHome(gene_id="TGME49_200250", site_id="toxodb"),
}
_ORTHO = {
    "PF3D7_0103400.1-p1": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb"),
    "TGME49_200250-t26_1-p1": GeneHome(gene_id="TGME49_200250", site_id="toxodb"),
}


def _on(
    origin: str, homes: dict[str, GeneHome], site_id: str, kind: SiteKind
) -> list[str]:
    return genes_on(origin, list(homes), homes, site_id=site_id, kind=kind)


@pytest.mark.parametrize(
    ("site_id", "kind", "shown"),
    [
        ("plasmodb", "genomics", ["PF3D7_0103400", "PF3D7_0110100"]),
        ("veupathdb", "portal", ["PF3D7_0103400", "PF3D7_0110100"]),
        ("orthomcl", "orthomcl", ["PF3D7_0103400", "PF3D7_0110100"]),
        ("toxodb", "genomics", []),
    ],
)
def test_a_genomics_set_shows_on_its_site_the_portal_and_orthomcl(
    site_id: str, kind: SiteKind, shown: list[str]
) -> None:
    assert _on("plasmodb", _PLASMO, site_id, kind) == shown


@pytest.mark.parametrize(
    ("site_id", "kind", "shown"),
    [
        ("veupathdb", "portal", ["PF3D7_0103400", "PF3D7_0110100", "TGME49_200250"]),
        ("plasmodb", "genomics", ["PF3D7_0103400", "PF3D7_0110100"]),
        ("toxodb", "genomics", ["TGME49_200250"]),
        ("orthomcl", "orthomcl", ["PF3D7_0103400", "PF3D7_0110100", "TGME49_200250"]),
        ("cryptodb", "genomics", []),
    ],
)
def test_a_portal_set_shows_each_site_its_own_genes(
    site_id: str, kind: SiteKind, shown: list[str]
) -> None:
    assert _on("veupathdb", _PORTAL, site_id, kind) == shown


@pytest.mark.parametrize(
    ("site_id", "kind", "shown"),
    [
        ("orthomcl", "orthomcl", ["PF3D7_0103400.1-p1", "TGME49_200250-t26_1-p1"]),
        ("plasmodb", "genomics", ["PF3D7_0103400"]),
        ("toxodb", "genomics", ["TGME49_200250"]),
        ("veupathdb", "portal", ["PF3D7_0103400", "TGME49_200250"]),
    ],
)
def test_an_orthomcl_protein_set_shows_each_site_its_gene_ids(
    site_id: str, kind: SiteKind, shown: list[str]
) -> None:
    assert _on("orthomcl", _ORTHO, site_id, kind) == shown


def test_a_set_of_records_that_are_not_genes_shows_on_its_own_site_only() -> None:
    groups = ["OG7_0001234", "OG7_0005678"]
    places: tuple[tuple[str, SiteKind], ...] = (
        ("orthomcl", "orthomcl"),
        ("plasmodb", "genomics"),
        ("veupathdb", "portal"),
    )

    assert [
        genes_on("orthomcl", groups, {}, site_id=site_id, kind=kind)
        for site_id, kind in places
    ] == [groups, [], []]
