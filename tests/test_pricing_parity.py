"""The shared fixture behind the Python/TypeScript parity contract.

webui/src/pricing.test.ts runs the same cases. If these two ever disagree the
designer would show a different number from `awsgraph estimate`.
"""

import json
from pathlib import Path

import pytest

from awsgraph.build import build
from awsgraph.estimate import estimate
from awsgraph.load import parse_design
from awsgraph.pricing import PricingCatalog

FIXTURE = json.loads(Path("tests/fixtures/pricing_cases.json").read_text(encoding="utf-8"))
CATALOG = PricingCatalog.from_mapping(FIXTURE["catalog"], "pricing_cases.json")


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: c["name"])
def test_python_matches_the_parity_fixture(case):
    graph = build(parse_design({"metadata": {"name": "parity"}, "resources": [case["resource"]]}))
    estimate(graph, CATALOG)
    attrs = graph.nodes[case["resource"]["id"]]
    assert attrs["monthly_cost"] == case["expected_monthly_cost"]
    assert attrs["cost_status"] == case["expected_status"]


def test_fixture_covers_every_priced_resource_type():
    covered = {case["resource"]["resource_type"] for case in FIXTURE["cases"]}
    assert covered == {"ec2", "ebs", "rds", "alb", "nat-gateway"}
