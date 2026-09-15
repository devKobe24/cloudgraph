"""Per-service pricing maths against a catalog with round numbers."""

from decimal import Decimal

import pytest

from awsgraph.build import build
from awsgraph.estimate import estimate
from awsgraph.load import parse_design
from awsgraph.pricing import PricingCatalog

CATALOG = PricingCatalog.from_file("tests/fixtures/pricing/test-catalog.json")


def price(resource):
    graph = build(parse_design({"metadata": {"name": "T"}, "resources": [resource]}))
    estimate(graph, CATALOG)
    return graph.nodes[resource["id"]]


def test_ebs_size_times_count():
    # 0.1000 * 50 GiB * 2 volumes
    node = price(
        {
            "id": "v",
            "name": "Vol",
            "resource_type": "ebs",
            "configuration": {"size_gib": 50},
            "usage": {"volume_count": 2},
        }
    )
    assert node["monthly_cost"] == "10.00"
    assert node["cost_status"] == "priced"


def test_ebs_partial_month():
    node = price(
        {
            "id": "v",
            "name": "Vol",
            "resource_type": "ebs",
            "configuration": {"size_gib": 100},
            "usage": {"volume_count": 1, "month_fraction": 0.5},
        }
    )
    assert node["monthly_cost"] == "5.00"


def test_rds_splits_compute_and_storage():
    # compute 0.2000 * 100 h ; storage 0.1000 * 100 GiB
    node = price(
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
        }
    )
    assert node["monthly_cost"] == "30.00"
    assert node["cost_breakdown"] == [
        {"name": "instance hours", "amount": "20.00", "unit": "USD"},
        {"name": "storage", "amount": "10.00", "unit": "USD"},
    ]


def test_rds_storage_scales_with_instance_count():
    node = price(
        {
            "id": "d",
            "name": "DB",
            "resource_type": "rds",
            "configuration": {
                "engine": "mysql",
                "instance_class": "db.t3.medium",
                "storage_gib": 100,
            },
            "usage": {"instance_count": 2, "hours_per_month": 100},
        }
    )
    assert node["monthly_cost"] == "60.00"


def test_alb_fixed_plus_lcu():
    # 0.0200 * 100 h + 0.0100 * 500 LCU-h
    node = price(
        {
            "id": "lb",
            "name": "ALB",
            "resource_type": "alb",
            "usage": {
                "load_balancer_count": 1,
                "hours_per_month": 100,
                "lcu_hours_per_month": 500,
            },
        }
    )
    assert node["monthly_cost"] == "7.00"
    assert [item["name"] for item in node["cost_breakdown"]] == [
        "load balancer hours",
        "LCU hours",
    ]


def test_nat_fixed_plus_processing():
    # 0.0400 * 100 h + 0.0500 * 200 GB
    node = price(
        {
            "id": "n",
            "name": "NAT",
            "resource_type": "nat-gateway",
            "usage": {
                "gateway_count": 1,
                "hours_per_month": 100,
                "processed_gb_per_month": 200,
            },
        }
    )
    assert node["monthly_cost"] == "14.00"


def test_one_missing_rate_is_partial_not_silently_cheap():
    # The test catalog prices mysql but not postgres; storage still resolves.
    node = price(
        {
            "id": "d",
            "name": "DB",
            "resource_type": "rds",
            "configuration": {
                "engine": "postgres",
                "instance_class": "db.t3.medium",
                "storage_gib": 100,
            },
            "usage": {"instance_count": 1, "hours_per_month": 100},
        }
    )
    assert node["cost_status"] == "partial"
    assert node["monthly_cost"] == "10.00"
    assert node["cost_missing"] == ["missing price: rds/postgres/single-az/on-demand/db.t3.medium"]


def test_every_missing_rate_is_unpriced():
    node = price(
        {
            "id": "n",
            "name": "NAT",
            "resource_type": "nat-gateway",
            "usage": {
                "gateway_count": 1,
                "hours_per_month": 100,
                "processed_gb_per_month": 200,
            },
        }
    )
    assert node["cost_status"] == "priced"  # sanity: this catalog does price NAT


def test_zero_usage_stays_priced_at_zero():
    node = price(
        {
            "id": "n",
            "name": "NAT",
            "resource_type": "nat-gateway",
            "usage": {
                "gateway_count": 1,
                "hours_per_month": 0,
                "processed_gb_per_month": 0,
            },
        }
    )
    assert node["monthly_cost"] == "0.00"
    assert node["cost_status"] == "priced"


@pytest.mark.parametrize(
    "resource_type", ["ec2", "ebs", "rds", "alb", "nat-gateway", "vpc", "subnet"]
)
def test_every_v01_resource_type_has_a_calculator(resource_type):
    from awsgraph.pricing import CALCULATORS

    assert resource_type in CALCULATORS


def test_bundled_catalog_prices_the_three_tier_example():
    from awsgraph.load import load_design
    from awsgraph.pricing import load_catalog

    architecture = load_design("tests/fixtures/three-tier.awsgraph.json")
    graph = build(architecture)
    summary = estimate(graph, load_catalog("ap-northeast-2", "ap-northeast-2-2026-09"))

    assert summary["status"] == "priced"
    assert summary["unpriced_resource_ids"] == []
    node_total = sum(Decimal(a["monthly_cost"]) for _, a in graph.nodes(data=True))
    assert Decimal(summary["monthly_cost"]) == node_total
