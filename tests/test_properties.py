"""Property-based tests. These look for shapes of input the examples miss."""

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from awsgraph.analyze import analyze
from awsgraph.build import build
from awsgraph.estimate import estimate
from awsgraph.export import to_json_payload
from awsgraph.load import DesignError, parse_design
from awsgraph.pricing import PricingCatalog, to_money
from awsgraph.validate import CONNECTION_RULES, validate_design

CATALOG = PricingCatalog.from_file("tests/fixtures/pricing/test-catalog.json")

ids = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=12)
names = st.text(min_size=1, max_size=20).filter(lambda s: s.strip())


@st.composite
def ec2_resources(draw, count=5):
    chosen = draw(st.lists(ids, min_size=1, max_size=count, unique=True))
    return [
        {
            "id": rid,
            "name": draw(names),
            "resource_type": "ec2",
            "configuration": {"instance_type": "t3.medium"},
            "usage": {
                "instance_count": draw(st.integers(min_value=1, max_value=50)),
                "hours_per_month": draw(st.floats(min_value=0, max_value=744, allow_nan=False)),
            },
        }
        for rid in chosen
    ]


@settings(max_examples=50, deadline=None)
@given(resources=ec2_resources())
def test_build_keeps_one_node_per_resource(resources):
    architecture = parse_design({"metadata": {"name": "T"}, "resources": resources})
    graph = build(architecture)
    assert graph.number_of_nodes() == len(resources)
    assert set(graph.nodes) == {r["id"] for r in resources}


@settings(max_examples=50, deadline=None)
@given(resources=ec2_resources())
def test_total_always_equals_the_sum_of_nodes(resources):
    graph = build(parse_design({"metadata": {"name": "T"}, "resources": resources}))
    summary = estimate(graph, CATALOG)
    node_total = sum(Decimal(a["monthly_cost"]) for _, a in graph.nodes(data=True))
    assert Decimal(summary["monthly_cost"]) == to_money(node_total)


@settings(max_examples=50, deadline=None)
@given(resources=ec2_resources())
def test_json_round_trip_preserves_the_graph(resources):
    import json
    import tempfile
    from pathlib import Path

    from awsgraph.load import load_graph

    graph = build(parse_design({"metadata": {"name": "T"}, "resources": resources}))
    estimate(graph, CATALOG)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "graph.json"
        path.write_text(json.dumps(to_json_payload(graph)), encoding="utf-8")
        back = load_graph(path)
    assert back.number_of_nodes() == graph.number_of_nodes()
    assert back.number_of_edges() == graph.number_of_edges()
    for node_id, attrs in graph.nodes(data=True):
        assert back.nodes[node_id]["monthly_cost"] == attrs["monthly_cost"]


@settings(max_examples=50, deadline=None)
@given(
    pairs=st.lists(st.sampled_from(sorted(CONNECTION_RULES)), min_size=1, max_size=6, unique=True)
)
def test_valid_relationships_never_leave_a_dangling_edge(pairs):
    from awsgraph.schema import RESOURCE_TYPES

    def resource(rid, rtype):
        node = {"id": rid, "name": rid, "resource_type": rtype}
        if rtype == "ec2":
            node["configuration"] = {"instance_type": "t3.medium"}
            node["usage"] = {"instance_count": 1, "hours_per_month": 1}
        elif rtype == "rds":
            node["configuration"] = {
                "engine": "mysql",
                "instance_class": "db.t3.medium",
                "storage_gib": 20,
            }
            node["usage"] = {"instance_count": 1, "hours_per_month": 1}
        elif rtype == "ebs":
            node["configuration"] = {"size_gib": 1}
            node["usage"] = {"volume_count": 1}
        elif rtype == "alb":
            node["usage"] = {
                "load_balancer_count": 1,
                "hours_per_month": 1,
                "lcu_hours_per_month": 0,
            }
        elif rtype == "nat-gateway":
            node["usage"] = {"gateway_count": 1, "hours_per_month": 1, "processed_gb_per_month": 0}
        return node

    used = {t for pair in pairs for t in pair}
    assert used <= set(RESOURCE_TYPES)
    resources = [resource(t, t) for t in sorted(used)]
    relationships = [
        {
            "id": f"e{i}",
            "source": source,
            "target": target,
            "relation": sorted(CONNECTION_RULES[(source, target)])[0],
        }
        for i, (source, target) in enumerate(pairs)
    ]
    architecture = parse_design(
        {"metadata": {"name": "T"}, "resources": resources, "relationships": relationships}
    )
    assert validate_design(architecture) == []
    graph = build(architecture)
    for source, target, _ in graph.edges(keys=True):
        assert source in graph and target in graph


@settings(max_examples=50, deadline=None)
@given(hours=st.floats(min_value=0, max_value=744, allow_nan=False))
def test_cost_is_never_negative_and_always_two_decimals(hours):
    graph = build(
        parse_design(
            {
                "metadata": {"name": "T"},
                "resources": [
                    {
                        "id": "a",
                        "name": "A",
                        "resource_type": "ec2",
                        "configuration": {"instance_type": "t3.medium"},
                        "usage": {"instance_count": 1, "hours_per_month": hours},
                    }
                ],
            }
        )
    )
    estimate(graph, CATALOG)
    cost = graph.nodes["a"]["monthly_cost"]
    assert Decimal(cost) >= 0
    assert cost.split(".")[1] == cost.split(".")[1][:2] and len(cost.split(".")[1]) == 2


@settings(max_examples=30, deadline=None)
@given(hours=st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False))
def test_negative_hours_are_always_rejected(hours):
    import pytest

    with pytest.raises(DesignError):
        parse_design(
            {
                "metadata": {"name": "T"},
                "resources": [
                    {
                        "id": "a",
                        "name": "A",
                        "resource_type": "ec2",
                        "configuration": {"instance_type": "t3.medium"},
                        "usage": {"instance_count": 1, "hours_per_month": hours},
                    }
                ],
            }
        )


@settings(max_examples=30, deadline=None)
@given(resources=ec2_resources())
def test_analyze_never_raises_on_a_valid_graph(resources):
    graph = build(parse_design({"metadata": {"name": "T"}, "resources": resources}))
    estimate(graph, CATALOG)
    analysis = analyze(graph)
    assert analysis["summary"]["node_count"] == len(resources)
