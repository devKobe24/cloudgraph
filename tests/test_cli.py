import json
import subprocess
import sys
from pathlib import Path

import pytest

from awsgraph import __version__
from awsgraph.cli import SUBCOMMANDS, main
from awsgraph.schema import DEFAULT_CATALOG_ID


def run(*args):
    return subprocess.run([sys.executable, "-m", "awsgraph", *args], capture_output=True, text=True)


def test_help_lists_every_subcommand():
    result = run("--help")
    assert result.returncode == 0
    for name in SUBCOMMANDS:
        assert name in result.stdout


def test_version():
    result = run("--version")
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_no_args_prints_help():
    assert main([]) == 0


def test_every_advertised_command_is_implemented():
    # Until Phase 7 this guarded the stub path. Every subcommand in --help now
    # has a handler, so the useful assertion is that none is left advertised-only.
    from awsgraph.cli import COMMANDS

    assert set(SUBCOMMANDS) == set(COMMANDS)


def test_unknown_command_exits_nonzero():
    with pytest.raises(SystemExit) as exc:
        main(["nope"])
    assert exc.value.code != 0


def test_init_creates_a_valid_design_file(tmp_path):
    path = tmp_path / "architecture.awsgraph.json"
    assert main(["init", str(path)]) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "0.1"
    assert data["metadata"]["name"] == "My AWS Architecture"
    assert data["pricing_context"]["catalog_id"] == DEFAULT_CATALOG_ID
    assert data["resources"] == []
    assert data["relationships"] == []
    assert data["layout"] == {"positions": {}}
    assert main(["validate", str(path)]) == 0


def test_init_refuses_to_overwrite(tmp_path):
    path = tmp_path / "a.json"
    path.write_text("keep me", encoding="utf-8")
    assert main(["init", str(path)]) == 1
    assert path.read_text(encoding="utf-8") == "keep me"
    assert main(["init", str(path), "--force"]) == 0


def test_validate_ok():
    assert main(["validate", "tests/fixtures/ec2.awsgraph.json"]) == 0


def test_validate_reports_path_prefixed_errors(tmp_path, capsys):
    path = tmp_path / "bad.awsgraph.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"name": "T"},
                "resources": [
                    {
                        "id": "res_ec2",
                        "name": "Backend",
                        "resource_type": "ec2",
                        "configuration": {"instance_type": "t3.medium"},
                        "usage": {"instance_count": 1, "hours_per_month": 745},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["validate", str(path)]) == 1
    assert "resources[0].usage.hours_per_month" in capsys.readouterr().err


def test_build_writes_three_artifacts(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["build", "tests/fixtures/ec2.awsgraph.json", "--out", str(out)]) == 0
    assert (out / "graph.json").is_file()
    assert (out / "graph.html").is_file()
    assert (out / "AWS_REPORT.md").is_file()
    assert "75.92" in capsys.readouterr().out


def test_build_rejects_an_invalid_design(tmp_path, capsys):
    bad = tmp_path / "bad.awsgraph.json"
    bad.write_text(
        json.dumps(
            {
                "metadata": {"name": "T"},
                "resources": [
                    {
                        "id": "a",
                        "name": "A",
                        "resource_type": "ec2",
                        "configuration": {"instance_type": "t3.medium"},
                        "usage": {"instance_count": 1, "hours_per_month": 730},
                    },
                    {"id": "b", "name": "B", "resource_type": "vpc"},
                ],
                "relationships": [
                    {"id": "e1", "source": "a", "target": "b", "relation": "contains"}
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["build", str(bad), "--out", str(tmp_path / "out")]) == 1
    assert not (tmp_path / "out").exists()
    assert "no relationship is allowed" in capsys.readouterr().err


def test_build_warns_about_unpriced_resources(tmp_path, capsys):
    design = tmp_path / "d.awsgraph.json"
    design.write_text(
        json.dumps(
            {
                "metadata": {"name": "T"},
                "resources": [
                    {
                        "id": "a",
                        "name": "Backend",
                        "resource_type": "ec2",
                        "configuration": {"instance_type": "t4g.nano"},
                        "usage": {"instance_count": 1, "hours_per_month": 730},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["build", str(design), "--out", str(tmp_path / "out")]) == 0
    captured = capsys.readouterr()
    assert "could not be priced" in captured.err
    assert "ec2/linux/shared/on-demand/t4g.nano" in captured.err
    assert "$0.00 (partial)" in captured.out


def test_build_catalog_mismatch(tmp_path, capsys):
    design = json.loads(open("tests/fixtures/ec2.awsgraph.json", encoding="utf-8").read())
    design["pricing_context"]["catalog_id"] = "ap-northeast-2-1999-01"
    path = tmp_path / "d.awsgraph.json"
    path.write_text(json.dumps(design), encoding="utf-8")
    assert main(["build", str(path), "--out", str(tmp_path / "out")]) == 1
    assert "asks for catalog" in capsys.readouterr().err


def test_estimate_reads_the_built_graph(tmp_path, capsys):
    out = tmp_path / "out"
    main(["build", "tests/fixtures/ec2.awsgraph.json", "--out", str(out)])
    capsys.readouterr()
    assert main(["estimate", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "Estimated Monthly Cost" in printed
    assert "$75.92" in printed
    assert "EC2" in printed


def test_estimate_json_output(tmp_path, capsys):
    out = tmp_path / "out"
    main(["build", "tests/fixtures/ec2.awsgraph.json", "--out", str(out)])
    capsys.readouterr()
    assert main(["estimate", "--out", str(out), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["monthly_cost"] == "75.92"
    assert data["cost_by_service"]["EC2"] == "75.92"


def test_estimate_without_a_build(tmp_path, capsys):
    assert main(["estimate", "--out", str(tmp_path / "nothing")]) == 1
    assert "awsgraph build" in capsys.readouterr().err


def test_build_does_not_touch_the_design_file(tmp_path):
    before = open("tests/fixtures/ec2.awsgraph.json", "rb").read()
    main(["build", "tests/fixtures/ec2.awsgraph.json", "--out", str(tmp_path / "out")])
    assert open("tests/fixtures/ec2.awsgraph.json", "rb").read() == before


def test_build_makes_no_network_calls(tmp_path, monkeypatch):
    import socket

    def boom(*args, **kwargs):
        raise AssertionError("build attempted a network call")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    assert main(["build", "tests/fixtures/ec2.awsgraph.json", "--out", str(tmp_path / "out")]) == 0


@pytest.fixture
def built(tmp_path):
    out = tmp_path / "out"
    main(["build", "tests/fixtures/ec2.awsgraph.json", "--out", str(out)])
    return out


@pytest.fixture
def built_three_tier(tmp_path):
    out = tmp_path / "out"
    main(["build", "tests/fixtures/three-tier.awsgraph.json", "--out", str(out)])
    return out


def test_stats(built, capsys):
    capsys.readouterr()
    assert main(["stats", "--out", str(built)]) == 0
    printed = capsys.readouterr().out
    assert "Resources: 3" in printed
    assert "contains: 2" in printed


def test_query(built, capsys):
    capsys.readouterr()
    assert main(["query", "backend", "--out", str(built)]) == 0
    assert "Backend EC2" in capsys.readouterr().out


def test_query_without_matches_exits_nonzero(built, capsys):
    capsys.readouterr()
    assert main(["query", "kubernetes", "--out", str(built)]) == 1
    assert "No resource matches" in capsys.readouterr().out


def test_explain(built, capsys):
    capsys.readouterr()
    assert main(["explain", "Backend EC2", "--out", str(built)]) == 0
    assert "Monthly estimate: $75.92" in capsys.readouterr().out


def test_explain_reports_a_fuzzy_match(built, capsys):
    capsys.readouterr()
    assert main(["explain", "backnd ec2", "--out", str(built)]) == 0
    captured = capsys.readouterr()
    assert "fuzzy label match" in captured.err
    assert "Node: Backend EC2" in captured.out


def test_explain_unknown_resource(built, capsys):
    capsys.readouterr()
    assert main(["explain", "zzzzz", "--out", str(built)]) == 1
    assert "no resource matches" in capsys.readouterr().err


def test_explain_ambiguous_lists_candidates(tmp_path, capsys):
    design = tmp_path / "d.awsgraph.json"
    node = {
        "resource_type": "ec2",
        "configuration": {"instance_type": "t3.medium"},
        "usage": {"instance_count": 1, "hours_per_month": 730},
    }
    design.write_text(
        json.dumps(
            {
                "metadata": {"name": "T"},
                "resources": [
                    {"id": "a", "name": "Backend", **node},
                    {"id": "b", "name": "Backend", **node},
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    main(["build", str(design), "--out", str(out)])
    capsys.readouterr()

    assert main(["explain", "Backend", "--out", str(out)]) == 1
    err = capsys.readouterr().err
    assert "matches more than one resource" in err
    assert "(a)" in err and "(b)" in err


def test_path(built, capsys):
    capsys.readouterr()
    assert main(["path", "Main VPC", "Backend EC2", "--out", str(built)]) == 0
    assert "Main VPC --contains--> App Subnet --contains--> Backend EC2" in capsys.readouterr().out


def test_path_against_direction_exits_nonzero(built, capsys):
    capsys.readouterr()
    assert main(["path", "Backend EC2", "Main VPC", "--out", str(built)]) == 1
    assert "No path from" in capsys.readouterr().err


def test_query_commands_need_a_build(tmp_path, capsys):
    missing = str(tmp_path / "nothing")
    for argv in (["stats"], ["query", "x"], ["explain", "x"], ["path", "a", "b"]):
        assert main([*argv, "--out", missing]) == 1
    assert "awsgraph build" in capsys.readouterr().err


def test_three_tier_build_and_query(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["build", "tests/fixtures/three-tier.awsgraph.json", "--out", str(out)]) == 0
    printed = capsys.readouterr()
    assert "$287.54 (priced)" in printed.out
    assert printed.err == ""  # nothing unpriced

    assert main(["estimate", "--out", str(out)]) == 0
    estimate_output = capsys.readouterr().out
    for service in ("EC2", "EBS", "RDS", "ALB", "NAT Gateway"):
        assert service in estimate_output

    assert main(["path", "Public ALB", "Main RDS", "--out", str(out)]) == 0
    assert (
        "Public ALB --connects-to--> Backend EC2 --connects-to--> Main RDS"
        in capsys.readouterr().out
    )

    assert main(["path", "App Subnet", "Public NAT", "--out", str(out)]) == 0
    assert "--routes-to-->" in capsys.readouterr().out


def test_affected_follows_relation_direction(built_three_tier, capsys):
    capsys.readouterr()
    assert main(["affected", "Main RDS", "--out", str(built_three_tier)]) == 0
    printed = capsys.readouterr().out
    assert "Backend EC2" in printed and "Public ALB" in printed

    assert main(["affected", "Main VPC", "--depth", "1", "--out", str(built_three_tier)]) == 0
    depth_one = capsys.readouterr().out
    assert "App Subnet" in depth_one
    assert "Backend EC2" not in depth_one


def test_affected_unknown_resource(built_three_tier, capsys):
    capsys.readouterr()
    assert main(["affected", "zzzz", "--out", str(built_three_tier)]) == 1
    assert "no resource matches" in capsys.readouterr().err


def test_layout_positions_reach_the_viewer(tmp_path):
    design = json.loads(open("tests/fixtures/ec2.awsgraph.json", encoding="utf-8").read())
    out = tmp_path / "out"
    main(["build", "tests/fixtures/ec2.awsgraph.json", "--out", str(out)])
    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    placed = {n["id"]: n.get("position") for n in graph["nodes"]}
    assert placed["res_ec2"] == design["layout"]["positions"]["res_ec2"]


def test_viewer_has_no_position_when_the_design_omits_it(tmp_path):
    design = tmp_path / "d.awsgraph.json"
    design.write_text(
        json.dumps(
            {
                "metadata": {"name": "T"},
                "resources": [{"id": "v", "name": "VPC", "resource_type": "vpc"}],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    main(["build", str(design), "--out", str(out)])
    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    assert "position" not in graph["nodes"][0]


def test_design_writes_a_standalone_html(tmp_path, capsys, monkeypatch):
    import webbrowser

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    assert main(["design", "tests/fixtures/three-tier.awsgraph.json"]) == 0
    assert len(opened) == 1

    printed = capsys.readouterr().out
    path = Path(printed.splitlines()[0].removeprefix("Designer: "))
    assert path.is_file()
    assert "Three Tier" in path.read_text(encoding="utf-8")


def test_design_no_open(capsys, monkeypatch):
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda url: pytest.fail("should not open"))
    assert main(["design", "tests/fixtures/ec2.awsgraph.json", "--no-open"]) == 0
    assert "Designer:" in capsys.readouterr().out


def test_design_rejects_an_invalid_file(tmp_path, capsys):
    bad = tmp_path / "bad.awsgraph.json"
    bad.write_text(json.dumps({"metadata": {"name": "T"}, "resources": [{"id": "a"}]}), "utf-8")
    assert main(["design", str(bad)]) == 1
    assert "is invalid" in capsys.readouterr().err


def test_designer_export_round_trips_through_the_pipeline(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["build", "tests/fixtures/designer-export.awsgraph.json", "--out", str(out)]) == 0
    assert (out / "graph.json").is_file()
    assert capsys.readouterr().err == ""


def test_export_graphml(built_three_tier, capsys):
    capsys.readouterr()
    assert main(["export", "--out", str(built_three_tier)]) == 0
    path = built_three_tier / "graph.graphml"
    assert path.is_file()

    import networkx as nx

    graph = nx.read_graphml(path)
    assert graph.number_of_nodes() == 9
    assert graph.number_of_edges() == 11
    # Nested attributes survive as JSON text because GraphML holds scalars only.
    assert json.loads(graph.nodes["ec2"]["configuration"])["instance_type"] == "t3.medium"


def test_export_needs_a_build(tmp_path, capsys):
    assert main(["export", "--out", str(tmp_path / "nothing")]) == 1
    assert "awsgraph build" in capsys.readouterr().err
