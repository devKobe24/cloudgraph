import json

import networkx as nx
import pytest

from awsgraph import report
from awsgraph.analyze import analyze
from awsgraph.build import build
from awsgraph.estimate import estimate
from awsgraph.export import DATA_ELEMENT_ID, to_html, to_json_payload
from awsgraph.load import DesignError, load_graph, parse_design
from awsgraph.paths import write_json_atomic, write_text_atomic
from awsgraph.pricing import PricingCatalog

CATALOG = PricingCatalog.from_file("tests/fixtures/pricing/test-catalog.json")

DESIGN = {
    "metadata": {"name": "T"},
    "resources": [
        {"id": "s", "name": "Subnet", "resource_type": "subnet"},
        {
            "id": "a",
            "name": "Backend",
            "resource_type": "ec2",
            "configuration": {"instance_type": "t3.medium"},
            "usage": {"instance_count": 2, "hours_per_month": 730},
        },
        {
            "id": "n",
            "name": "NAT",
            "resource_type": "nat-gateway",
            "usage": {"gateway_count": 1, "hours_per_month": 730, "processed_gb_per_month": 10},
        },
    ],
    "relationships": [
        {"id": "e1", "source": "s", "target": "a", "relation": "contains"},
        {"id": "e2", "source": "s", "target": "n", "relation": "contains"},
        {"id": "e3", "source": "s", "target": "n", "relation": "routes-to"},
    ],
}


@pytest.fixture
def costed():
    graph = build(parse_design(DESIGN))
    estimate(graph, CATALOG)
    return graph


def test_payload_is_versioned_and_multigraph(costed):
    payload = to_json_payload(costed)
    assert payload["awsgraph_schema_version"] == "0.1"
    assert payload["directed"] is True
    assert payload["multigraph"] is True


def test_round_trip_preserves_everything(costed, tmp_path):
    path = tmp_path / "graph.json"
    write_json_atomic(path, to_json_payload(costed))
    back = load_graph(path)

    assert back.number_of_nodes() == costed.number_of_nodes()
    assert back.number_of_edges() == costed.number_of_edges()
    assert set(back.edges(keys=True)) == set(costed.edges(keys=True))
    assert back.nodes["a"]["monthly_cost"] == costed.nodes["a"]["monthly_cost"]
    assert back.nodes["a"]["configuration"] == costed.nodes["a"]["configuration"]
    assert back.graph["estimate"] == costed.graph["estimate"]


def test_round_trip_keeps_parallel_edges(costed, tmp_path):
    path = tmp_path / "graph.json"
    write_json_atomic(path, to_json_payload(costed))
    back = load_graph(path)
    relations = {attrs["relation"] for *_, attrs in back.edges(data=True) }
    assert {"contains", "routes-to"} <= relations
    assert back.number_of_edges() == 3


def test_money_survives_as_a_string(costed, tmp_path):
    path = tmp_path / "graph.json"
    write_json_atomic(path, to_json_payload(costed))
    raw = json.loads(path.read_text(encoding="utf-8"))
    node = next(n for n in raw["nodes"] if n["id"] == "a")
    assert node["monthly_cost"] == "75.92"
    assert isinstance(node["monthly_cost"], str)


def test_corrupt_graph_json_gives_a_recovery_hint(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(DesignError) as exc:
        load_graph(path)
    assert "not valid JSON" in exc.value.messages[0]
    assert "awsgraph build" in exc.value.messages[1]


def test_missing_graph_json_gives_a_recovery_hint(tmp_path):
    with pytest.raises(DesignError, match="awsgraph build"):
        load_graph(tmp_path / "graph.json")


def test_unknown_artifact_version_rejected(tmp_path):
    path = tmp_path / "graph.json"
    payload = to_json_payload(nx.MultiDiGraph())
    payload["awsgraph_schema_version"] = "9.9"
    write_json_atomic(path, payload)
    with pytest.raises(DesignError, match="unsupported graph artifact version"):
        load_graph(path)


def test_html_embeds_graph_data(costed):
    html_text = to_html(costed)
    assert DATA_ELEMENT_ID in html_text
    assert "75.92" in html_text
    assert "http://" not in html_text and "https://" not in html_text


def test_html_does_not_execute_a_malicious_label():
    design = json.loads(json.dumps(DESIGN))
    design["resources"][1]["name"] = "</script><script>alert(1)</script>"
    graph = build(parse_design(design))
    estimate(graph, CATALOG)
    html_text = to_html(graph)

    # Only the data block opens a script tag, and the label cannot close it.
    assert html_text.count("<script") == 1
    assert "</script><script>" not in html_text
    assert "&lt;/script&gt;" in html_text  # rendered as text in the table
    assert "\\u003c/script\\u003e" in html_text  # escaped inside the JSON block


def test_report_contains_the_required_facts(costed):
    text = report.generate(costed, analyze(costed), source="design.json")
    for expected in (
        "75.92",
        "ap-northeast-2",
        "test-catalog",
        "not an AWS bill",
        "Savings Plans",
        "Unpriced Resources",
    ):
        assert expected in text


def test_report_flags_unpriced_resources(costed):
    text = report.generate(costed, analyze(costed))
    assert "NAT (NAT Gateway)" in text
    assert "no calculator for resource type 'nat-gateway'" in text


def test_report_is_deterministic(costed):
    first = report.generate(costed, analyze(costed), source="design.json")
    second = report.generate(costed, analyze(costed), source="design.json")
    assert first == second


def test_atomic_write_keeps_the_old_file_when_writing_fails(tmp_path):
    path = tmp_path / "graph.json"
    write_text_atomic(path, "original")

    class Boom:
        def __repr__(self):
            raise RuntimeError("boom")

    with pytest.raises((RuntimeError, TypeError)):
        write_json_atomic(path, {"bad": Boom()})
    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob(".*tmp")) == []
