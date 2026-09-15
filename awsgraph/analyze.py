"""Read-only analysis of a costed graph. Writes no files (guide section 7.1)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import networkx as nx


def analyze(graph: nx.MultiDiGraph) -> dict:
    by_service: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    unpriced: list[dict] = []

    for node_id, attrs in graph.nodes(data=True):
        by_service[attrs["service"]] += Decimal(attrs.get("monthly_cost", "0"))
        if attrs.get("cost_status") != "priced":
            unpriced.append(
                {
                    "id": node_id,
                    "label": attrs["label"],
                    "service": attrs["service"],
                    "missing": attrs.get("cost_missing", []),
                }
            )

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
            for service, amount in sorted(
                by_service.items(), key=lambda kv: (-kv[1], kv[0])
            )
        },
        "unpriced": unpriced,
    }
