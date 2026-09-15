import pytest

from awsgraph.build import build
from awsgraph.estimate import estimate
from awsgraph.load import parse_design
from awsgraph.pricing import PricingCatalog
from awsgraph.query import (
    render_explain,
    render_path,
    render_search,
    render_stats,
    resolve,
    search,
)

CATALOG = PricingCatalog.from_file("tests/fixtures/pricing/test-catalog.json")


def ec2(rid, name, instance_type="t3.medium"):
    return {
        "id": rid,
        "name": name,
        "resource_type": "ec2",
        "configuration": {"instance_type": instance_type},
        "usage": {"instance_count": 1, "hours_per_month": 730},
    }


DESIGN = {
    "metadata": {"name": "T"},
    "resources": [
        {"id": "res_vpc", "name": "Main VPC", "resource_type": "vpc"},
        {"id": "res_subnet", "name": "App Subnet", "resource_type": "subnet"},
        ec2("res_ec2", "Backend EC2"),
    ],
    "relationships": [
        {"id": "e1", "source": "res_vpc", "target": "res_subnet", "relation": "contains"},
        {"id": "e2", "source": "res_subnet", "target": "res_ec2", "relation": "contains"},
    ],
}


@pytest.fixture
def graph():
    g = build(parse_design(DESIGN))
    estimate(g, CATALOG)
    return g


# --- resolution ------------------------------------------------------------


def test_exact_id_wins(graph):
    result = resolve(graph, "res_ec2")
    assert result.ids == ["res_ec2"] and result.how == "id"


def test_exact_label(graph):
    result = resolve(graph, "Backend EC2")
    assert result.ids == ["res_ec2"] and result.how == "label"


def test_case_insensitive_label(graph):
    result = resolve(graph, "backend ec2")
    assert result.ids == ["res_ec2"]
    assert result.how == "label (case-insensitive)"


def test_resource_type_resolution(graph):
    result = resolve(graph, "ec2")
    assert result.ids == ["res_ec2"] and result.how == "resource type"


def test_fuzzy_label(graph):
    result = resolve(graph, "backnd ec2")
    assert result.ids == ["res_ec2"] and result.how == "fuzzy label match"


def test_no_match(graph):
    assert resolve(graph, "zzzzzz").ids == []


def test_ambiguous_label_returns_every_candidate():
    design = dict(DESIGN, resources=[ec2("a", "Backend"), ec2("b", "Backend")], relationships=[])
    graph = build(parse_design(design))
    result = resolve(graph, "Backend")
    assert sorted(result.ids) == ["a", "b"]
    assert not result.is_unique


def test_resource_type_matching_many_is_ambiguous():
    design = dict(DESIGN, resources=[ec2("a", "One"), ec2("b", "Two")], relationships=[])
    result = resolve(build(parse_design(design)), "ec2")
    assert sorted(result.ids) == ["a", "b"]


# --- search ----------------------------------------------------------------


def test_search_finds_by_label(graph):
    assert search(graph, "backend") == ["res_ec2"]


def test_search_finds_by_type(graph):
    assert search(graph, "subnet") == ["res_subnet"]


def test_search_empty_text(graph):
    assert search(graph, "   ") == []


def test_search_no_match(graph):
    assert search(graph, "kubernetes") == []


def test_render_search_includes_connections(graph):
    rendered = render_search(graph, "backend")
    assert "Matches:" in rendered
    assert "Backend EC2 [ec2] $37.96" in rendered
    assert "App Subnet --contains--> Backend EC2" in rendered


# --- explain ---------------------------------------------------------------


def test_explain_shows_config_usage_cost_and_links(graph):
    rendered = render_explain(graph, "res_ec2")
    assert "Node: Backend EC2" in rendered
    assert "Type: ec2 (EC2)" in rendered
    assert "Monthly estimate: $37.96 (priced)" in rendered
    assert "instance_type: t3.medium" in rendered
    assert "instance_count: 1" in rendered
    assert "<-- App Subnet [contains]" in rendered


def test_explain_structural_node_has_no_usage_block(graph):
    rendered = render_explain(graph, "res_vpc")
    assert "Usage:" not in rendered
    assert "--> App Subnet [contains]" in rendered


# --- path ------------------------------------------------------------------


def test_path_renders_relations(graph):
    assert (
        render_path(graph, "res_vpc", "res_ec2")
        == "Main VPC --contains--> App Subnet --contains--> Backend EC2"
    )


def test_path_respects_direction(graph):
    assert render_path(graph, "res_ec2", "res_vpc") is None


def test_path_names_every_parallel_relation():
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
    assert render_path(graph, "s", "n") == "Subnet --contains | routes-to--> NAT"


# --- stats -----------------------------------------------------------------


def test_stats(graph):
    rendered = render_stats(graph)
    assert "Resources: 3" in rendered
    assert "  ec2: 1" in rendered
    assert "Relationships: 2" in rendered
    assert "  contains: 2" in rendered
    assert "Estimated monthly cost: $37.96 (priced)" in rendered
