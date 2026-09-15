"""graph.json and graph.html.

The HTML is standalone: no network requests, no external assets. Phase 5 swaps
the body for the React Flow viewer; the embedded JSON block stays the contract.
"""

from __future__ import annotations

import html
import json
from importlib import resources

import networkx as nx

ARTIFACT_VERSION = "0.1"
DATA_ELEMENT_ID = "awsgraph-data"
DATA_TOKEN = "__AWSGRAPH_DATA__"
TITLE_TOKEN = "__AWSGRAPH_TITLE__"


def to_json_payload(graph: nx.MultiDiGraph) -> dict:
    payload = nx.node_link_data(graph, edges="edges")
    payload["awsgraph_schema_version"] = ARTIFACT_VERSION
    return payload


def json_for_html(data: object) -> str:
    """Escape so the payload cannot terminate the <script> block it lives in."""
    raw = json.dumps(data, ensure_ascii=False)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _template() -> str:
    return (resources.files("awsgraph") / "assets" / "viewer.html").read_text(encoding="utf-8")


def to_html(graph: nx.MultiDiGraph) -> str:
    """Standalone viewer: the template plus this graph's data, nothing fetched."""
    title = html.escape(graph.graph.get("architecture_name", "AWSGraph"))
    return (
        _template()
        .replace(TITLE_TOKEN, title)
        .replace(DATA_TOKEN, json_for_html(to_json_payload(graph)))
    )


def _flatten(value: object) -> str | int | float | bool:
    """GraphML holds scalars only, so nested attributes travel as JSON text."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False)


def to_graphml(graph: nx.MultiDiGraph) -> str:
    flat = nx.MultiDiGraph()
    flat.graph.update({key: _flatten(value) for key, value in graph.graph.items()})
    for node_id, attrs in graph.nodes(data=True):
        flat.add_node(node_id, **{key: _flatten(value) for key, value in attrs.items()})
    for source, target, key, attrs in graph.edges(keys=True, data=True):
        flat.add_edge(source, target, key=key, **{k: _flatten(v) for k, v in attrs.items()})
    return "\n".join(nx.generate_graphml(flat)) + "\n"


FORMATS = {"graphml": (to_graphml, "graph.graphml")}
