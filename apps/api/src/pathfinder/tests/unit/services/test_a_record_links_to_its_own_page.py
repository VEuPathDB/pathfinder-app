"""A record links to the site's page of its own record type."""

from __future__ import annotations

from pathfinder.services.record_pages import record_page_url


def test_an_ortholog_group_links_to_the_group_page() -> None:
    assert (
        record_page_url("orthomcl", "group", "OG8_0001941")
        == "https://qa.orthomcl.org/orthomcl.qa/app/record/group/OG8_0001941"
    )


def test_a_protein_links_to_the_sequence_page() -> None:
    assert (
        record_page_url("orthomcl", "sequence", "A0H76_3082-t39_1-p1")
        == "https://qa.orthomcl.org/orthomcl.qa/app/record/sequence/A0H76_3082-t39_1-p1"
    )


def test_a_gene_a_transcript_step_lists_links_to_the_gene_page() -> None:
    assert (
        record_page_url("plasmodb", "transcript", "PF3D7_1133400")
        == "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_1133400"
    )
