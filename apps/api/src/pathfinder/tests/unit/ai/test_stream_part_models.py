"""Tests for typed stream-part payload models."""

import pytest
from pydantic import ValidationError

from pathfinder.ai.stream_part_payloads import (
    GeneSet,
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    StrategyLink,
    StrategyMeta,
)


def test_graph_snapshot_validates_required_fields():
    snapshot = GraphSnapshot(
        strategy_id="s_abc123",
        gene_count=87,
        nodes=[
            GraphNode(
                id="n1",
                search_name="GenesByOrthologPattern",
                estimated_size=342,
            )
        ],
        edges=[GraphEdge(source="n1", target="n2", operator="INTERSECT")],
    )
    assert snapshot.strategy_id == "s_abc123"
    assert snapshot.gene_count == 87
    assert len(snapshot.nodes) == 1


def test_graph_snapshot_rejects_missing_strategy_id():
    with pytest.raises(ValidationError):
        GraphSnapshot(gene_count=0, nodes=[], edges=[])


def test_graph_snapshot_rejects_negative_gene_count():
    with pytest.raises(ValidationError):
        GraphSnapshot(strategy_id="s_x", gene_count=-1, nodes=[], edges=[])


def test_strategy_meta_validates():
    meta = StrategyMeta(
        strategy_id="s_x",
        name="My strategy",
        is_saved=False,
        estimated_size=42,
        record_class_name="transcript",
    )
    assert meta.name == "My strategy"


def test_strategy_link_validates():
    link = StrategyLink(
        strategy_id="s_x",
        url="https://plasmodb.org/plasmo/app/record/dataset/s_x",
        title="My strategy",
    )
    assert link.url.startswith("https://")


def test_gene_set_validates():
    gs = GeneSet(
        gene_set_id="gs_1",
        name="exported-proteins",
        gene_count=87,
        site_id="plasmodb",
    )
    assert gs.gene_count == 87


# ── Wire-contract tests ─────────────────────────────────────────────────────
# These lock the camelCase alias behavior, snake_case acceptance via
# populate_by_name, and extra-field tolerance. Without them, a flip of
# alias_generator or extra="ignore" in CamelModel passes all the field-validation
# tests above but silently breaks the frontend contract.


def test_camel_model_accepts_camel_case_input():
    snapshot = GraphSnapshot.model_validate(
        {
            "strategyId": "s_abc",
            "geneCount": 42,
            "nodes": [{"id": "n1", "searchName": "ByText", "estimatedSize": 10}],
            "edges": [{"source": "n1", "target": "n2", "operator": "INTERSECT"}],
        }
    )
    assert snapshot.strategy_id == "s_abc"
    assert snapshot.gene_count == 42
    assert snapshot.nodes[0].search_name == "ByText"


def test_camel_model_accepts_snake_case_input_via_populate_by_name():
    snapshot = GraphSnapshot.model_validate(
        {
            "strategy_id": "s_abc",
            "gene_count": 42,
            "nodes": [],
            "edges": [],
        }
    )
    assert snapshot.strategy_id == "s_abc"


def test_camel_model_emits_camel_case_on_by_alias_dump():
    snapshot = GraphSnapshot(
        strategy_id="s_abc",
        gene_count=42,
        nodes=[GraphNode(id="n1", search_name="ByText", estimated_size=10)],
        edges=[GraphEdge(source="n1", target="n2", operator="INTERSECT")],
    )
    dumped = snapshot.model_dump(by_alias=True)
    assert "strategyId" in dumped
    assert "geneCount" in dumped
    assert "strategy_id" not in dumped
    assert "searchName" in dumped["nodes"][0]


def test_camel_model_ignores_extra_fields():
    # `extra="ignore"` on CamelModel means protocol additions from newer servers
    # don't crash old clients. Unknown fields are dropped silently.
    snapshot = GraphSnapshot.model_validate(
        {
            "strategyId": "s_abc",
            "geneCount": 0,
            "nodes": [],
            "edges": [],
            "futureField": "should be dropped",
            "anotherExtra": 12345,
        }
    )
    assert snapshot.strategy_id == "s_abc"
    # Confirm the extras aren't smuggled through
    dumped = snapshot.model_dump(by_alias=True)
    assert "futureField" not in dumped
    assert "anotherExtra" not in dumped


def test_graph_edge_operator_accepts_all_seven_wdk_operators():
    """GraphEdge.operator must match WDK's full BooleanOperator set."""
    for op in ("INTERSECT", "UNION", "MINUS", "RMINUS", "LONLY", "RONLY", "COLOCATE"):
        edge = GraphEdge(source="a", target="b", operator=op)
        assert edge.operator == op


def test_graph_edge_operator_rejects_unknown_operator():
    with pytest.raises(ValidationError):
        GraphEdge(source="a", target="b", operator="TELEPORT")
