from awsgraph.affected import affected, render_affected
from awsgraph.build import build
from awsgraph.load import load_design, parse_design

THREE_TIER = build(load_design("tests/fixtures/three-tier.awsgraph.json"))


def labels(graph, start, depth=None):
    return [item["label"] for item in affected(graph, start, depth)]


def test_connects_to_walks_incoming():
    # Changing the database affects whoever connects to it, then their callers.
    assert labels(THREE_TIER, "rds") == ["Backend EC2", "Public ALB"]


def test_contains_walks_outgoing():
    assert labels(THREE_TIER, "vpc", depth=1) == ["App Subnet", "DB Subnet", "Public Subnet"]


def test_contains_reaches_contents_at_depth_two():
    assert labels(THREE_TIER, "vpc") == [
        "App Subnet",
        "DB Subnet",
        "Public Subnet",
        "Backend EC2",
        "Main RDS",
        "Public ALB",
        "Public NAT",
    ]


def test_attached_to_walks_incoming():
    assert "Backend EC2" in labels(THREE_TIER, "vol")


def test_routes_to_walks_incoming():
    # The subnet that egresses through the NAT depends on it.
    assert "App Subnet" in labels(THREE_TIER, "nat")


def test_depth_limit():
    assert labels(THREE_TIER, "rds", depth=1) == ["Backend EC2"]


def test_depth_is_recorded():
    hits = {item["label"]: item["depth"] for item in affected(THREE_TIER, "rds")}
    assert hits == {"Backend EC2": 1, "Public ALB": 2}


def test_leaf_affects_nothing():
    assert affected(THREE_TIER, "alb") == []


def test_start_node_is_never_in_its_own_result():
    assert "Main VPC" not in labels(THREE_TIER, "vpc")


def test_no_duplicate_nodes_from_parallel_edges():
    # Public Subnet both contains and (from App Subnet) routes to the NAT.
    result = labels(THREE_TIER, "pub")
    assert len(result) == len(set(result))


def test_parallel_relations_are_both_reported():
    design = {
        "metadata": {"name": "T"},
        "resources": [
            {"id": "s", "name": "Subnet", "resource_type": "subnet"},
            {
                "id": "n",
                "name": "NAT",
                "resource_type": "nat-gateway",
                "usage": {
                    "gateway_count": 1,
                    "hours_per_month": 730,
                    "processed_gb_per_month": 1,
                },
            },
        ],
        "relationships": [
            {"id": "e1", "source": "s", "target": "n", "relation": "contains"},
            {"id": "e2", "source": "s", "target": "n", "relation": "routes-to"},
        ],
    }
    graph = build(parse_design(design))
    # From the NAT: routes-to is followed incoming, contains is not.
    assert [item["via"] for item in affected(graph, "n")] == [["routes-to"]]
    # From the subnet: contains is followed outgoing.
    assert [item["via"] for item in affected(graph, "s")] == [["contains"]]


def test_cycles_terminate():
    design = {
        "metadata": {"name": "T"},
        "resources": [
            {"id": "s1", "name": "S1", "resource_type": "subnet"},
            {"id": "s2", "name": "S2", "resource_type": "subnet"},
            {"id": "v", "name": "V", "resource_type": "vpc"},
        ],
        "relationships": [
            {"id": "e1", "source": "v", "target": "s1", "relation": "contains"},
            {"id": "e2", "source": "v", "target": "s2", "relation": "contains"},
        ],
    }
    graph = build(parse_design(design))
    # Hand-build a cycle the schema would reject, to prove traversal terminates.
    graph.add_edge("s1", "s2", key="x", id="x", relation="contains", provenance={})
    graph.add_edge("s2", "s1", key="y", id="y", relation="contains", provenance={})
    assert sorted(labels(graph, "v")) == ["S1", "S2"]


def test_render_groups_by_depth():
    rendered = render_affected(THREE_TIER, "rds")
    assert "Affected by a change to Main RDS:" in rendered
    assert "depth 1:" in rendered
    assert "  Backend EC2 (EC2) [connects-to]" in rendered
    assert "depth 2:" in rendered


def test_render_when_nothing_depends_on_it():
    assert render_affected(THREE_TIER, "alb") == "Nothing depends on Public ALB."
