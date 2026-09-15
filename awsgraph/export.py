"""graph.json and graph.html.

The HTML is standalone: no network requests, no external assets. Phase 5 swaps
the body for the React Flow viewer; the embedded JSON block stays the contract.
"""

from __future__ import annotations

import html
import json

import networkx as nx

ARTIFACT_VERSION = "0.1"
DATA_ELEMENT_ID = "awsgraph-data"


def to_json_payload(graph: nx.MultiDiGraph) -> dict:
    payload = nx.node_link_data(graph, edges="edges")
    payload["awsgraph_schema_version"] = ARTIFACT_VERSION
    return payload


def json_for_html(data: object) -> str:
    """Escape so the payload cannot terminate the <script> block it lives in."""
    raw = json.dumps(data, ensure_ascii=False)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _rows(graph: nx.MultiDiGraph) -> str:
    currency = graph.graph.get("currency", "USD")
    rows = []
    for _, attrs in sorted(graph.nodes(data=True), key=lambda kv: kv[1]["label"]):
        rows.append(
            "<tr>"
            f"<td>{html.escape(attrs['label'])}</td>"
            f"<td>{html.escape(attrs['resource_type'])}</td>"
            f"<td class='num'>{html.escape(attrs.get('monthly_cost', '0'))} {html.escape(currency)}</td>"
            f"<td>{html.escape(attrs.get('cost_status', 'unknown'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _edges(graph: nx.MultiDiGraph) -> str:
    items = []
    for source, target, attrs in graph.edges(data=True):
        items.append(
            "<li>"
            f"{html.escape(graph.nodes[source]['label'])} "
            f"<code>{html.escape(attrs['relation'])}</code> "
            f"{html.escape(graph.nodes[target]['label'])}"
            "</li>"
        )
    return "\n".join(items) or "<li>No relationships defined.</li>"


def to_html(graph: nx.MultiDiGraph) -> str:
    meta = graph.graph
    estimate = meta.get("estimate", {})
    title = html.escape(meta.get("architecture_name", "AWSGraph"))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — AWSGraph</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 60rem; padding: 0 1rem; }}
  h1 {{ margin-bottom: 0; }}
  .meta {{ color: #666; font-size: 13px; }}
  .total {{ font-size: 2rem; font-weight: 600; margin: 1rem 0; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border-bottom: 1px solid #8884; padding: .4rem .6rem; text-align: left; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  code {{ background: #8882; padding: 0 .3rem; border-radius: 3px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="meta">{html.escape(meta.get('region', ''))} ·
catalog {html.escape(meta.get('catalog_id', ''))} ·
AWSGraph {html.escape(meta.get('product_version', ''))}</p>

<p class="total">{html.escape(estimate.get('monthly_cost', '0'))}
{html.escape(estimate.get('currency', 'USD'))} / month</p>

<h2>Resources</h2>
<table>
<thead><tr><th>Name</th><th>Type</th><th class="num">Monthly</th><th>Status</th></tr></thead>
<tbody>
{_rows(graph)}
</tbody>
</table>

<h2>Relationships</h2>
<ul>
{_edges(graph)}
</ul>

<script type="application/json" id="{DATA_ELEMENT_ID}">
{json_for_html(to_json_payload(graph))}
</script>
</body>
</html>
"""
