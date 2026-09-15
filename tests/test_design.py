"""The designer asset, and the file the designer writes."""

import json
import re

import pytest

from awsgraph.design import DATA_BLOCK, open_designer, render
from awsgraph.load import load_design, parse_design
from awsgraph.pricing import PricingCatalog, load_catalog
from awsgraph.schema import RESOURCE_TYPES
from awsgraph.validate import CONNECTION_RULES, validate_design

EXPORT = "tests/fixtures/designer-export.awsgraph.json"
CATALOG = PricingCatalog.from_file("tests/fixtures/pricing/test-catalog.json")


def small_design():
    return parse_design(
        {
            "metadata": {"name": "T"},
            "resources": [
                {
                    "id": "a",
                    "name": "Backend",
                    "resource_type": "ec2",
                    "configuration": {"instance_type": "t3.medium"},
                    "usage": {"instance_count": 1, "hours_per_month": 730},
                }
            ],
        }
    )


# --- what the designer writes ---------------------------------------------


def test_designer_export_validates():
    architecture = load_design(EXPORT)
    assert validate_design(architecture) == []


def test_designer_export_covers_every_resource_type():
    architecture = load_design(EXPORT)
    assert {r.resource_type for r in architecture.resources} == set(RESOURCE_TYPES)


def test_designer_export_covers_every_connection_rule():
    architecture = load_design(EXPORT)
    types = {r.id: r.resource_type for r in architecture.resources}
    drawn = {
        (types[rel.source], types[rel.target], rel.relation) for rel in architecture.relationships
    }
    expected = {
        (source, target, relation)
        for (source, target), relations in CONNECTION_RULES.items()
        for relation in relations
    }
    assert drawn == expected


def test_designer_export_has_no_usage_on_structural_resources():
    raw = json.loads(open(EXPORT, encoding="utf-8").read())
    for resource in raw["resources"]:
        if resource["resource_type"] in {"vpc", "subnet"}:
            assert "usage" not in resource


# --- rendering the designer ------------------------------------------------


def test_render_replaces_only_the_data_element():
    html = render(small_design(), CATALOG)
    match = DATA_BLOCK.search(html)
    assert match is not None
    payload = json.loads(
        match.group(2).replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&")
    )
    assert payload["architecture"]["resources"][0]["name"] == "Backend"
    assert payload["catalog"]["catalog_id"] == "test-catalog"


def test_render_keeps_the_bundle_intact():
    # The bundle contains the placeholder as a string literal; replacing it there
    # used to corrupt the JavaScript.
    html = render(small_design(), CATALOG)
    assert "__AWSGRAPH_DESIGN__" in html  # still present inside the bundle
    assert DATA_BLOCK.search(html).group(2).strip() != "__AWSGRAPH_DESIGN__"


def test_render_escapes_a_malicious_name():
    architecture = parse_design(
        {
            "metadata": {"name": "T"},
            "resources": [
                {
                    "id": "a",
                    "name": "</script><script>alert(1)</script>",
                    "resource_type": "vpc",
                }
            ],
        }
    )
    html = render(architecture, CATALOG)
    assert "</script><script>alert" not in html
    assert "\\u003c/script\\u003e" in html


def test_render_embeds_the_catalog_rates():
    html = render(small_design(), CATALOG)
    assert "ec2/linux/shared/on-demand/t3.medium" in html


def test_open_designer_writes_a_file_without_opening_a_browser(tmp_path, monkeypatch):
    import webbrowser

    monkeypatch.setattr(
        webbrowser, "open", lambda *a, **k: pytest.fail("should not open a browser")
    )
    path = open_designer(small_design(), CATALOG, open_browser=False)
    assert path.is_file()
    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_designer_asset_pulls_no_subresources():
    """The only ways the markup can fetch at load are script src and link href.

    Searching the bundle for strings like "fetch(" is meaningless -- React ships
    those in its own source. What matters is that vite inlined everything.
    """
    html = render(small_design(), load_catalog("ap-northeast-2"))
    assert re.search(r"<script[^>]*\ssrc=", html) is None
    assert re.search(r"<link[^>]*\shref=", html) is None
    assert re.search(r'<img[^>]*\ssrc="(?!data:)', html) is None


def test_missing_designer_asset_is_a_clean_error(tmp_path, monkeypatch):
    from awsgraph import design as design_module

    monkeypatch.setattr(design_module, "_asset", lambda: tmp_path / "gone.html")
    with pytest.raises(design_module.DesignerAssetError, match="no designer asset"):
        render(small_design(), CATALOG)


def test_designer_built_without_a_data_element_is_a_clean_error(tmp_path, monkeypatch):
    from awsgraph import design as design_module

    broken = tmp_path / "designer.html"
    broken.write_text("<!doctype html><html><body>no data block</body></html>", encoding="utf-8")
    monkeypatch.setattr(design_module, "_asset", lambda: broken)
    with pytest.raises(design_module.DesignerAssetError, match="no data element"):
        render(small_design(), CATALOG)
