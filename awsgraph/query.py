"""Query helpers over a built graph.

These read graph.json, never the design file (guide section 8.3). Resolution is
deliberately conservative: an ambiguous term returns every candidate instead of
picking one (guide section 21.1).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import networkx as nx
from rapidfuzz import fuzz, process, utils

FUZZY_CUTOFF = 70
SEARCH_CUTOFF = 60


def format_money(amount: str, currency: str) -> str:
    return f"${amount}" if currency == "USD" else f"{amount} {currency}"


def _currency(graph: nx.MultiDiGraph) -> str:
    return graph.graph.get("currency", "USD")


def describe(graph: nx.MultiDiGraph, node_id: str) -> str:
    attrs = graph.nodes[node_id]
    return f"{attrs['label']} [{attrs['resource_type']}] ({node_id})"


# --- node resolution -------------------------------------------------------


@dataclass(frozen=True)
class Resolution:
    ids: list[str]
    how: str

    @property
    def is_unique(self) -> bool:
        return len(self.ids) == 1


def resolve(graph: nx.MultiDiGraph, term: str) -> Resolution:
    if term in graph:
        return Resolution([term], "id")

    nodes = list(graph.nodes(data=True))

    exact = [n for n, a in nodes if a["label"] == term]
    if exact:
        return Resolution(exact, "label")

    lowered = term.lower()
    insensitive = [n for n, a in nodes if a["label"].lower() == lowered]
    if insensitive:
        return Resolution(insensitive, "label (case-insensitive)")

    by_kind = [
        n
        for n, a in nodes
        if a["resource_type"].lower() == lowered or a["service"].lower() == lowered
    ]
    if by_kind:
        return Resolution(by_kind, "resource type")

    labels = {n: a["label"] for n, a in nodes}
    # default_process lowercases and strips punctuation; without it "backnd ec2"
    # scores 67 against "Backend EC2" and falls under the cutoff.
    hits = process.extract(
        term,
        labels,
        scorer=fuzz.WRatio,
        processor=utils.default_process,
        score_cutoff=FUZZY_CUTOFF,
        limit=5,
    )
    return Resolution([node_id for _, _, node_id in hits], "fuzzy label match")


# --- search ----------------------------------------------------------------


def search(graph: nx.MultiDiGraph, text: str, limit: int = 10) -> list[str]:
    """Score whitespace-separated tokens against label, type and service."""
    tokens = text.lower().split()
    if not tokens:
        return []

    scored: list[tuple[float, str]] = []
    for node_id, attrs in graph.nodes(data=True):
        haystack = f"{attrs['label']} {attrs['resource_type']} {attrs['service']}".lower()
        total = 0.0
        for token in tokens:
            # Substring first so prefixes ("back") score full marks; token_set_ratio
            # only has to cover typos. partial_ratio was too generous here -- it
            # scored "kubernetes" 67 against "app subnet".
            total += 100.0 if token in haystack else fuzz.token_set_ratio(token, haystack)
        score = total / len(tokens)
        if score >= SEARCH_CUTOFF:
            scored.append((score, node_id))

    scored.sort(key=lambda pair: (-pair[0], graph.nodes[pair[1]]["label"]))
    return [node_id for _, node_id in scored[:limit]]


def render_search(graph: nx.MultiDiGraph, text: str, limit: int = 10) -> str:
    seeds = search(graph, text, limit)
    if not seeds:
        return f'No resource matches "{text}".'

    lines = ["Matches:"]
    for node_id in seeds:
        attrs = graph.nodes[node_id]
        lines.append(
            f"- {attrs['label']} [{attrs['resource_type']}] "
            f"{format_money(attrs.get('monthly_cost', '0'), _currency(graph))}"
        )

    seed_set = set(seeds)
    connections = [
        f"{graph.nodes[s]['label']} --{a['relation']}--> {graph.nodes[t]['label']}"
        for s, t, a in graph.edges(data=True)
        if s in seed_set or t in seed_set
    ]
    if connections:
        lines += ["", "Connections:", *connections]
    return "\n".join(lines)


# --- explain ---------------------------------------------------------------


def render_explain(graph: nx.MultiDiGraph, node_id: str) -> str:
    attrs = graph.nodes[node_id]
    currency = _currency(graph)
    lines = [
        f"Node: {attrs['label']}",
        f"Id: {node_id}",
        f"Type: {attrs['resource_type']} ({attrs['service']})",
        f"Region: {attrs['region']}",
        f"Monthly estimate: {format_money(attrs.get('monthly_cost', '0'), currency)}"
        f" ({attrs.get('cost_status', 'unknown')})",
    ]

    for title, values in (
        ("Configuration", attrs.get("configuration") or {}),
        ("Usage", attrs.get("usage") or {}),
    ):
        if values:
            lines += ["", f"{title}:"]
            lines += [f"  {key}: {value}" for key, value in values.items()]

    breakdown = attrs.get("cost_breakdown") or []
    if breakdown:
        lines += ["", "Cost breakdown:"]
        lines += [
            f"  {item['name']}: {format_money(item['amount'], item.get('unit') or currency)}"
            for item in breakdown
        ]

    incoming = [
        f"  <-- {graph.nodes[s]['label']} [{a['relation']}]"
        for s, _, a in graph.in_edges(node_id, data=True)
    ]
    outgoing = [
        f"  --> {graph.nodes[t]['label']} [{a['relation']}]"
        for _, t, a in graph.out_edges(node_id, data=True)
    ]
    lines += ["", "Connections:"]
    lines += sorted(incoming) + sorted(outgoing) or ["  (none)"]

    for title, key in (("Assumptions", "cost_assumptions"), ("Missing", "cost_missing")):
        values = attrs.get(key) or []
        if values:
            lines += ["", f"{title}:"]
            lines += [f"  {value}" for value in values]

    return "\n".join(lines)


# --- path ------------------------------------------------------------------


def render_path(graph: nx.MultiDiGraph, source: str, target: str) -> str | None:
    """Return the rendered path, or None when the graph has none."""
    try:
        hops = nx.shortest_path(graph, source, target)
    except nx.NetworkXNoPath:
        return None

    parts = [graph.nodes[hops[0]]["label"]]
    for left, right in zip(hops, hops[1:]):
        # Parallel edges: name every relation that joins the pair.
        relations = sorted({a["relation"] for a in graph.get_edge_data(left, right).values()})
        parts.append(f"--{' | '.join(relations)}-->")
        parts.append(graph.nodes[right]["label"])
    return " ".join(parts)


# --- stats -----------------------------------------------------------------


def render_stats(graph: nx.MultiDiGraph) -> str:
    estimate = graph.graph.get("estimate", {})
    currency = _currency(graph)
    by_type = Counter(a["resource_type"] for _, a in graph.nodes(data=True))
    by_relation = Counter(a["relation"] for *_, a in graph.edges(data=True))

    lines = [
        f"Architecture: {graph.graph.get('architecture_name', 'unknown')}",
        f"Region: {graph.graph.get('region', 'unknown')}",
        f"Catalog: {graph.graph.get('catalog_id', 'unknown')}",
        "",
        f"Resources: {graph.number_of_nodes()}",
    ]
    lines += [f"  {name}: {count}" for name, count in sorted(by_type.items())]
    lines += ["", f"Relationships: {graph.number_of_edges()}"]
    lines += [f"  {name}: {count}" for name, count in sorted(by_relation.items())]
    lines += [
        "",
        f"Estimated monthly cost: {format_money(estimate.get('monthly_cost', '0'), currency)}"
        f" ({estimate.get('status', 'unknown')})",
    ]
    unpriced = estimate.get("unpriced_resource_ids", [])
    if unpriced:
        lines.append(f"Unpriced resources: {len(unpriced)}")
    return "\n".join(lines)
