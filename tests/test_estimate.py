from decimal import Decimal

import pytest

from awsgraph.analyze import analyze
from awsgraph.build import build
from awsgraph.estimate import estimate
from awsgraph.load import parse_design
from awsgraph.pricing import CatalogError, PricingCatalog, calculate_ec2, load_catalog

CATALOG = PricingCatalog.from_file("tests/fixtures/pricing/test-catalog.json")


def costed(resources):
    graph = build(parse_design({"metadata": {"name": "T"}, "resources": list(resources)}))
    summary = estimate(graph, CATALOG)
    return graph, summary


def ec2(rid="a", instance_type="t3.medium", count=2, hours=730):
    return {
        "id": rid,
        "name": rid,
        "resource_type": "ec2",
        "configuration": {"instance_type": instance_type},
        "usage": {"instance_count": count, "hours_per_month": hours},
    }


def test_ec2_monthly_cost():
    # 0.0520 * 730 * 2
    graph, summary = costed([ec2()])
    assert graph.nodes["a"]["monthly_cost"] == "75.92"
    assert graph.nodes["a"]["cost_status"] == "priced"
    assert summary["monthly_cost"] == "75.92"
    assert summary["status"] == "priced"


def test_zero_hours_costs_nothing_but_stays_priced():
    graph, _ = costed([ec2(hours=0)])
    assert graph.nodes["a"]["monthly_cost"] == "0.00"
    assert graph.nodes["a"]["cost_status"] == "priced"


def test_structural_nodes_are_free_and_priced():
    graph, summary = costed([{"id": "v", "name": "VPC", "resource_type": "vpc"}])
    assert graph.nodes["v"]["monthly_cost"] == "0.00"
    assert graph.nodes["v"]["cost_status"] == "priced"
    assert summary["status"] == "priced"


def test_missing_rate_is_unpriced_not_zero():
    graph, summary = costed([ec2(instance_type="t4g.large")])
    node = graph.nodes["a"]
    assert node["cost_status"] == "unpriced"
    assert node["cost_missing"] == [
        "missing price: ec2/linux/shared/on-demand/t4g.large"
    ]
    assert summary["status"] == "partial"
    assert summary["unpriced_resource_ids"] == ["a"]


def test_resource_without_a_calculator_is_unpriced():
    rds = {
        "id": "b",
        "name": "DB",
        "resource_type": "rds",
        "configuration": {"engine": "mysql", "instance_class": "db.t3.medium", "storage_gib": 100},
        "usage": {"instance_count": 1, "hours_per_month": 730},
    }
    graph, summary = costed([rds])
    assert graph.nodes["b"]["cost_status"] == "unpriced"
    assert summary["status"] == "partial"


def test_total_equals_the_sum_of_node_costs():
    graph, summary = costed([ec2("a"), ec2("b", "t3.small", 1, 100), ec2("c", hours=0)])
    node_total = sum(Decimal(attrs["monthly_cost"]) for _, attrs in graph.nodes(data=True))
    assert Decimal(summary["monthly_cost"]) == node_total


def test_decimal_math_not_float_math():
    # 0.0260 * 100 * 3 == 7.80 exactly; float arithmetic drifts here.
    graph, _ = costed([ec2("a", "t3.small", 3, 100)])
    assert graph.nodes["a"]["monthly_cost"] == "7.80"


def test_breakdown_recorded():
    graph, _ = costed([ec2()])
    assert graph.nodes["a"]["cost_breakdown"] == [
        {"name": "instance hours", "amount": "75.92", "unit": "USD"}
    ]


def test_analyze_summary_and_service_breakdown():
    graph, _ = costed([ec2("a"), {"id": "v", "name": "VPC", "resource_type": "vpc"}])
    analysis = analyze(graph)
    assert analysis["summary"]["node_count"] == 2
    assert analysis["summary"]["unpriced_count"] == 0
    assert analysis["cost_by_service"] == {"EC2": "75.92", "VPC": "0.00"}


def test_analyze_lists_unpriced_resources():
    graph, _ = costed([ec2(instance_type="t4g.large")])
    analysis = analyze(graph)
    assert analysis["summary"]["unpriced_count"] == 1
    assert analysis["unpriced"][0]["label"] == "a"


def test_catalog_lookup_returns_none_for_unknown_key():
    assert CATALOG.lookup("nope") is None
    assert CATALOG.lookup("ec2/linux/shared/on-demand/t3.medium") == Decimal("0.0520")


def test_bundled_catalog_loads():
    catalog = load_catalog("ap-northeast-2", "ap-northeast-2-2026-09")
    assert catalog.currency == "USD"
    assert catalog.lookup("ec2/linux/shared/on-demand/t3.medium") is not None


def test_catalog_id_mismatch_is_an_error():
    with pytest.raises(CatalogError, match="asks for catalog"):
        load_catalog("ap-northeast-2", "ap-northeast-2-1999-01")


def test_unknown_region_is_an_error():
    with pytest.raises(CatalogError, match="no pricing catalog"):
        load_catalog("us-east-1")


def test_calculator_takes_plain_dicts():
    result = calculate_ec2(
        {
            "instance_type": "t3.medium",
            "operating_system": "linux",
            "tenancy": "shared",
            "purchase_option": "on-demand",
        },
        {"instance_count": 1, "hours_per_month": 730},
        CATALOG,
    )
    assert result.monthly_cost == Decimal("37.96")
