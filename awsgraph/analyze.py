"""Read-only analysis of a costed graph. Writes no files (guide section 7.1)."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

import networkx as nx

# Nodes that exist to give the drawing structure rather than to cost money.
STRUCTURAL_TYPES = frozenset({"vpc", "subnet"})

HOTSPOT_LIMIT = 5
HUB_LIMIT = 5


def _cost(attrs: dict) -> Decimal:
    return Decimal(attrs.get("monthly_cost", "0"))


def analyze(graph: nx.MultiDiGraph) -> dict:
    by_service: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    unpriced: list[dict] = []
    hotspots: list[tuple[Decimal, str]] = []
    isolated: list[dict] = []

    for node_id, attrs in graph.nodes(data=True):
        cost = _cost(attrs)
        by_service[attrs["service"]] += cost

        if attrs.get("cost_status") != "priced":
            unpriced.append(
                {
                    "id": node_id,
                    "label": attrs["label"],
                    "service": attrs["service"],
                    "status": attrs.get("cost_status", "unknown"),
                    "missing": attrs.get("cost_missing", []),
                }
            )
        if cost > 0:
            hotspots.append((cost, node_id))
        if graph.degree(node_id) == 0:
            isolated.append(_brief(graph, node_id))

    hotspots.sort(key=lambda pair: (-pair[0], graph.nodes[pair[1]]["label"]))
    estimate = graph.graph.get("estimate", {})

    return {
        "summary": {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "service_count": len(by_service),
            "monthly_cost": estimate.get("monthly_cost", "0"),
            "currency": estimate.get("currency", "USD"),
            "unpriced_count": len(unpriced),
        },
        "cost_by_service": {
            service: str(amount)
            for service, amount in sorted(by_service.items(), key=lambda kv: (-kv[1], kv[0]))
        },
        "cost_hotspots": [
            {**_brief(graph, node_id), "monthly_cost": str(cost)}
            for cost, node_id in hotspots[:HOTSPOT_LIMIT]
        ],
        "dependency_hubs": _hubs(graph),
        "isolated": isolated,
        "unpriced": unpriced,
        "warnings": _warnings(graph),
    }


def _brief(graph: nx.MultiDiGraph, node_id: str) -> dict:
    attrs = graph.nodes[node_id]
    return {"id": node_id, "label": attrs["label"], "service": attrs["service"]}


def _hubs(graph: nx.MultiDiGraph) -> list[dict]:
    ranked = sorted(
        (
            (graph.in_degree(n) + graph.out_degree(n), n)
            for n in graph.nodes
            if graph.in_degree(n) + graph.out_degree(n) >= 2
        ),
        key=lambda pair: (-pair[0], graph.nodes[pair[1]]["label"]),
    )
    return [
        {
            **_brief(graph, node_id),
            "in_degree": graph.in_degree(node_id),
            "out_degree": graph.out_degree(node_id),
        }
        for _, node_id in ranked[:HUB_LIMIT]
    ]


def _containers(graph: nx.MultiDiGraph, node_id: str) -> list[str]:
    return [s for s, _, a in graph.in_edges(node_id, data=True) if a["relation"] == "contains"]


def _warnings(graph: nx.MultiDiGraph) -> list[dict]:
    """Conservative modelling warnings. These are not security findings."""
    warnings: list[dict] = []

    def add(kind: str, message: str, ids: list[str]) -> None:
        if ids:
            warnings.append({"kind": kind, "message": message, "resource_ids": ids})

    paid_unconnected = [
        n for n, a in graph.nodes(data=True) if graph.degree(n) == 0 and _cost(a) > 0
    ]
    add(
        "unconnected-paid-resource",
        "priced but connected to nothing, so it may be left over from an edit",
        paid_unconnected,
    )

    homeless = [
        n
        for n, a in graph.nodes(data=True)
        if a["resource_type"] in {"ec2", "rds"} and not _containers(graph, n)
    ]
    add(
        "no-containing-subnet",
        "compute or database resource that no subnet contains",
        homeless,
    )

    multi_homed = [n for n in graph.nodes if len(_containers(graph, n)) > 1]
    add(
        "multiple-containers",
        "contained by more than one resource; a real resource has one parent",
        multi_homed,
    )

    label_counts = Counter(a["label"] for _, a in graph.nodes(data=True))
    duplicates = [n for n, a in graph.nodes(data=True) if label_counts[a["label"]] > 1]
    add(
        "duplicate-name",
        "shares a name with another resource, which makes CLI lookups ambiguous",
        duplicates,
    )

    idle = [
        n
        for n, a in graph.nodes(data=True)
        if a["resource_type"] not in STRUCTURAL_TYPES
        and a.get("usage", {}).get("hours_per_month") == 0
    ]
    add(
        "zero-hours",
        "priced resource modelled as running 0 hours, so it contributes nothing",
        idle,
    )

    return warnings
