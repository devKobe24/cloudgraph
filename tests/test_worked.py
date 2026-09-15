"""Golden drift test for the worked examples.

graph.html carries no timestamp, but byte-comparing a 400 KB artifact would fail
on any cosmetic change. These compare the parts that carry meaning: counts,
costs, relations and the report's headline facts (guide section 29.2).
"""

import json
from pathlib import Path

import pytest

from awsgraph.analyze import analyze
from awsgraph.build import build
from awsgraph.estimate import estimate
from awsgraph.export import to_json_payload
from awsgraph.load import load_design
from awsgraph.pricing import load_catalog
from awsgraph.report import generate
from awsgraph.validate import validate_design

EXAMPLES = sorted(p.name for p in Path("worked").iterdir() if p.is_dir())


def comparable(payload: dict) -> dict:
    """The deterministic core of graph.json."""
    return {
        "estimate": payload["graph"]["estimate"],
        "nodes": sorted(
            (
                {
                    "id": n["id"],
                    "label": n["label"],
                    "resource_type": n["resource_type"],
                    "monthly_cost": n["monthly_cost"],
                    "cost_status": n["cost_status"],
                }
                for n in payload["nodes"]
            ),
            key=lambda n: n["id"],
        ),
        "edges": sorted(
            (e["source"], e["target"], e["key"], e["relation"]) for e in payload["edges"]
        ),
    }


@pytest.mark.parametrize("name", EXAMPLES)
def test_worked_example_is_valid(name):
    architecture = load_design(f"worked/{name}/architecture.awsgraph.json")
    assert validate_design(architecture) == []


@pytest.mark.parametrize("name", EXAMPLES)
def test_worked_output_matches_a_fresh_build(name):
    directory = Path("worked") / name
    architecture = load_design(directory / "architecture.awsgraph.json")
    graph = build(architecture)
    estimate(
        graph,
        load_catalog(architecture.pricing_context.region, architecture.pricing_context.catalog_id),
    )

    committed = json.loads((directory / "awsgraph-out" / "graph.json").read_text("utf-8"))
    assert comparable(to_json_payload(graph)) == comparable(committed)


@pytest.mark.parametrize("name", EXAMPLES)
def test_worked_report_headline_matches(name):
    directory = Path("worked") / name
    architecture = load_design(directory / "architecture.awsgraph.json")
    graph = build(architecture)
    estimate(
        graph,
        load_catalog(architecture.pricing_context.region, architecture.pricing_context.catalog_id),
    )
    fresh = generate(graph, analyze(graph), source=str(directory / "architecture.awsgraph.json"))
    committed = (directory / "awsgraph-out" / "AWS_REPORT.md").read_text("utf-8")

    def headline(text: str) -> list[str]:
        start = text.index("## Summary")
        end = text.index("## Cost Breakdown by Service")
        return [line for line in text[start:end].splitlines() if line.strip()]

    assert headline(fresh) == headline(committed)


@pytest.mark.parametrize("name", EXAMPLES)
def test_worked_example_ships_all_three_artifacts_and_a_review(name):
    directory = Path("worked") / name
    for filename in ("graph.json", "graph.html", "AWS_REPORT.md"):
        assert (directory / "awsgraph-out" / filename).is_file()
    review = (directory / "review.md").read_text("utf-8")
    assert "## Simplifications in the pricing" in review


def test_every_documented_example_exists():
    assert EXAMPLES == ["ec2-only", "ec2-rds", "three-tier"]
