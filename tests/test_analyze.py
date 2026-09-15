from awsgraph.analyze import analyze
from awsgraph.build import build
from awsgraph.estimate import estimate
from awsgraph.load import load_design, parse_design
from awsgraph.pricing import PricingCatalog, load_catalog

CATALOG = PricingCatalog.from_file("tests/fixtures/pricing/test-catalog.json")


def ec2(rid, name, count=1, hours=100):
    return {
        "id": rid,
        "name": name,
        "resource_type": "ec2",
        "configuration": {"instance_type": "t3.medium"},
        "usage": {"instance_count": count, "hours_per_month": hours},
    }


def analysed(resources, relationships=()):
    graph = build(
        parse_design(
            {
                "metadata": {"name": "T"},
                "resources": list(resources),
                "relationships": list(relationships),
            }
        )
    )
    estimate(graph, CATALOG)
    return graph, analyze(graph)


def warning_kinds(analysis):
    return {w["kind"] for w in analysis["warnings"]}


def test_hotspots_are_ranked_and_exclude_free_nodes():
    _, analysis = analysed(
        [
            ec2("big", "Big", count=4),
            ec2("small", "Small", count=1),
            {"id": "v", "name": "VPC", "resource_type": "vpc"},
        ]
    )
    assert [item["label"] for item in analysis["cost_hotspots"]] == ["Big", "Small"]
    assert analysis["cost_hotspots"][0]["monthly_cost"] == "20.80"


def test_isolated_resources():
    _, analysis = analysed(
        [{"id": "s", "name": "Subnet", "resource_type": "subnet"}, ec2("a", "A")],
        [{"id": "e1", "source": "s", "target": "a", "relation": "contains"}],
    )
    assert analysis["isolated"] == []

    _, analysis = analysed([ec2("a", "A")])
    assert [item["label"] for item in analysis["isolated"]] == ["A"]


def test_dependency_hubs_count_both_directions():
    _, analysis = analysed(
        [
            {"id": "s", "name": "Subnet", "resource_type": "subnet"},
            ec2("a", "A"),
            {
                "id": "d",
                "name": "DB",
                "resource_type": "rds",
                "configuration": {
                    "engine": "mysql",
                    "instance_class": "db.t3.medium",
                    "storage_gib": 100,
                },
                "usage": {"instance_count": 1, "hours_per_month": 100},
            },
        ],
        [
            {"id": "e1", "source": "s", "target": "a", "relation": "contains"},
            {"id": "e2", "source": "s", "target": "d", "relation": "contains"},
            {"id": "e3", "source": "a", "target": "d", "relation": "connects-to"},
        ],
    )
    hubs = {item["label"]: item for item in analysis["dependency_hubs"]}
    assert hubs["A"]["in_degree"] == 1 and hubs["A"]["out_degree"] == 1
    assert hubs["Subnet"]["out_degree"] == 2


def test_warns_about_a_paid_resource_with_no_connections():
    _, analysis = analysed([ec2("a", "Orphan")])
    assert "unconnected-paid-resource" in warning_kinds(analysis)


def test_free_resource_with_no_connections_is_not_a_paid_warning():
    _, analysis = analysed([{"id": "v", "name": "VPC", "resource_type": "vpc"}])
    assert "unconnected-paid-resource" not in warning_kinds(analysis)


def test_warns_about_compute_outside_a_subnet():
    _, analysis = analysed([ec2("a", "A")])
    assert "no-containing-subnet" in warning_kinds(analysis)


def test_no_subnet_warning_once_contained():
    _, analysis = analysed(
        [{"id": "s", "name": "Subnet", "resource_type": "subnet"}, ec2("a", "A")],
        [{"id": "e1", "source": "s", "target": "a", "relation": "contains"}],
    )
    assert "no-containing-subnet" not in warning_kinds(analysis)


def test_warns_about_two_containers():
    _, analysis = analysed(
        [
            {"id": "s1", "name": "S1", "resource_type": "subnet"},
            {"id": "s2", "name": "S2", "resource_type": "subnet"},
            ec2("a", "A"),
        ],
        [
            {"id": "e1", "source": "s1", "target": "a", "relation": "contains"},
            {"id": "e2", "source": "s2", "target": "a", "relation": "contains"},
        ],
    )
    assert "multiple-containers" in warning_kinds(analysis)


def test_warns_about_duplicate_names():
    _, analysis = analysed([ec2("a", "Same"), ec2("b", "Same")])
    duplicate = next(w for w in analysis["warnings"] if w["kind"] == "duplicate-name")
    assert sorted(duplicate["resource_ids"]) == ["a", "b"]


def test_warns_about_zero_hour_paid_resources():
    _, analysis = analysed([ec2("a", "Idle", hours=0)])
    assert "zero-hours" in warning_kinds(analysis)


def test_structural_nodes_never_trigger_zero_hours():
    _, analysis = analysed([{"id": "v", "name": "VPC", "resource_type": "vpc"}])
    assert "zero-hours" not in warning_kinds(analysis)


def test_three_tier_example_is_clean():
    graph = build(load_design("tests/fixtures/three-tier.awsgraph.json"))
    estimate(graph, load_catalog("ap-northeast-2", "ap-northeast-2-2026-09"))
    analysis = analyze(graph)

    assert analysis["summary"]["node_count"] == 9
    assert analysis["summary"]["edge_count"] == 11
    assert analysis["summary"]["unpriced_count"] == 0
    assert analysis["isolated"] == []
    assert analysis["warnings"] == []
    assert set(analysis["cost_by_service"]) == {
        "EC2",
        "EBS",
        "RDS",
        "ALB",
        "NAT Gateway",
        "VPC",
        "Subnet",
    }
