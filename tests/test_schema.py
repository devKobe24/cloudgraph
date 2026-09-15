import json

import pytest

from awsgraph import load as load_module
from awsgraph.load import DesignError, load_design, parse_design

FIXTURE = "tests/fixtures/ec2.awsgraph.json"


def design(**overrides):
    base = {
        "metadata": {"name": "T"},
        "resources": [
            {
                "id": "res_ec2",
                "name": "Backend",
                "resource_type": "ec2",
                "configuration": {"instance_type": "t3.medium"},
                "usage": {"instance_count": 1, "hours_per_month": 730},
            }
        ],
    }
    base.update(overrides)
    return base


def messages(data):
    with pytest.raises(DesignError) as exc:
        parse_design(data)
    return exc.value.messages


def test_valid_fixture_parses():
    architecture = load_design(FIXTURE)
    assert architecture.schema_version == "0.1"
    assert [r.resource_type for r in architecture.resources] == ["vpc", "subnet", "ec2"]
    assert architecture.resources[2].usage.instance_count == 2


def test_defaults_applied():
    architecture = parse_design(design())
    assert architecture.pricing_context.region == "ap-northeast-2"
    assert architecture.pricing_context.currency == "USD"
    assert architecture.resources[0].configuration.purchase_option == "on-demand"


def test_id_is_independent_of_name():
    data = design()
    before = parse_design(data).resources[0]
    data["resources"][0]["name"] = "API Backend"
    after = parse_design(data).resources[0]
    assert before.id == after.id
    assert before.name != after.name


def test_unknown_resource_type_rejected():
    data = design()
    data["resources"][0]["resource_type"] = "lambda"
    assert any("resource_type" in m for m in messages(data))


def test_negative_hours_rejected():
    data = design()
    data["resources"][0]["usage"]["hours_per_month"] = -1
    assert any(m.startswith("resources[0].usage.hours_per_month") for m in messages(data))


def test_hours_above_744_rejected():
    data = design()
    data["resources"][0]["usage"]["hours_per_month"] = 745
    found = messages(data)
    assert found == ["resources[0].usage.hours_per_month: Input should be less than or equal to 744"]


def test_zero_instance_count_rejected():
    data = design()
    data["resources"][0]["usage"]["instance_count"] = 0
    assert any(m.startswith("resources[0].usage.instance_count") for m in messages(data))


def test_unknown_field_rejected():
    data = design()
    data["resources"][0]["usage"]["cpu"] = 4
    assert any("cpu" in m for m in messages(data))


def test_multi_az_rds_rejected():
    data = design(
        resources=[
            {
                "id": "res_rds",
                "name": "DB",
                "resource_type": "rds",
                "configuration": {
                    "engine": "mysql",
                    "instance_class": "db.t3.medium",
                    "multi_az": True,
                    "storage_gib": 100,
                },
                "usage": {"instance_count": 1, "hours_per_month": 730},
            }
        ]
    )
    assert any(m.startswith("resources[0].configuration.multi_az") for m in messages(data))


def test_missing_file(tmp_path):
    with pytest.raises(DesignError) as exc:
        load_design(tmp_path / "nope.json")
    assert "nope.json" in exc.value.messages[0]


def test_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(DesignError) as exc:
        load_design(path)
    assert "invalid JSON" in exc.value.messages[0]


def test_size_cap(tmp_path, monkeypatch):
    path = tmp_path / "big.json"
    path.write_text(json.dumps(design()), encoding="utf-8")
    monkeypatch.setattr(load_module, "MAX_DESIGN_BYTES", 10)
    with pytest.raises(DesignError) as exc:
        load_design(path)
    assert "larger than" in exc.value.messages[0]
