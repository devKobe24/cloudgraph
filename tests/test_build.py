import networkx as nx
import pytest

from awsgraph.build import build
from awsgraph.load import parse_design

SUBNET = {"id": "s", "name": "Subnet", "resource_type": "subnet"}
EC2 = {
    "id": "a",
    "name": "Backend",
    "resource_type": "ec2",
    "configuration": {"instance_type": "t3.medium"},
    "usage": {"instance_count": 2, "hours_per_month": 730},
}
RDS = {
    "id": "b",
    "name": "DB",
    "resource_type": "rds",
    "configuration": {"engine": "mysql", "instance_class": "db.t3.medium", "storage_gib": 100},
    "usage": {"instance_count": 1, "hours_per_month": 730},
}


def graph_of(resources, relationships=()):
    return build(
        parse_design(
            {
                "metadata": {"name": "T"},
                "resources": list(resources),
                "relationships": list(relationships),
            }
        )
    )


def test_counts_match_the_design():
    graph = graph_of(
        [SUBNET, EC2, RDS],
        [
            {"id": "e1", "source": "s", "target": "a", "relation": "contains"},
            {"id": "e2", "source": "a", "target": "b", "relation": "connects-to"},
        ],
    )
    assert graph.number_of_nodes() == 3
    assert graph.number_of_edges() == 2


def test_graph_is_a_multidigraph():
    graph = graph_of([EC2])
    assert isinstance(graph, nx.MultiDiGraph)
    assert graph.is_directed() and graph.is_multigraph()


def test_node_attributes():
    attrs = graph_of([EC2]).nodes["a"]
    assert attrs["label"] == "Backend"
    assert attrs["resource_type"] == "ec2"
    assert attrs["service"] == "EC2"
    assert attrs["configuration"]["instance_type"] == "t3.medium"
    assert attrs["usage"]["instance_count"] == 2
    assert attrs["provenance"] == {"kind": "declared"}


def test_structural_node_has_empty_usage():
    assert graph_of([SUBNET]).nodes["s"]["usage"] == {}


def test_direction_and_relation_preserved():
    graph = graph_of(
        [EC2, RDS], [{"id": "e1", "source": "a", "target": "b", "relation": "connects-to"}]
    )
    assert list(graph.successors("a")) == ["b"]
    assert list(graph.successors("b")) == []
    assert graph["a"]["b"]["e1"]["relation"] == "connects-to"


def test_edge_key_is_the_relationship_id():
    graph = graph_of(
        [EC2, RDS], [{"id": "edge_42", "source": "a", "target": "b", "relation": "connects-to"}]
    )
    assert list(graph.edges(keys=True)) == [("a", "b", "edge_42")]


def test_parallel_edges_are_kept():
    nat = {
        "id": "n",
        "name": "NAT",
        "resource_type": "nat-gateway",
        "usage": {"gateway_count": 1, "hours_per_month": 730, "processed_gb_per_month": 10},
    }
    graph = graph_of(
        [SUBNET, nat],
        [
            {"id": "e1", "source": "s", "target": "n", "relation": "contains"},
            {"id": "e2", "source": "s", "target": "n", "relation": "routes-to"},
        ],
    )
    assert graph.number_of_edges() == 2
    assert {attrs["relation"] for *_, attrs in graph.edges(data=True)} == {
        "contains",
        "routes-to",
    }


def test_graph_metadata():
    graph = graph_of([EC2])
    assert graph.graph["schema_version"] == "0.1"
    assert graph.graph["region"] == "ap-northeast-2"
    assert graph.graph["currency"] == "USD"
    assert graph.graph["architecture_name"] == "T"


def test_duplicate_ids_raise_instead_of_collapsing():
    # validate_design catches this first; build must not silently lose a node.
    architecture = parse_design(
        {"metadata": {"name": "T"}, "resources": [EC2, {**EC2, "name": "Other"}]}
    )
    with pytest.raises(ValueError, match="duplicate resource ids"):
        build(architecture)
