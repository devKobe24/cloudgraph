"""Walk the graph, price every node, record the result on the graph."""

from __future__ import annotations

from decimal import Decimal

import networkx as nx

from .pricing import CALCULATORS, CostEstimate, PricingCatalog, to_money, unpriced


def estimate(graph: nx.MultiDiGraph, catalog: PricingCatalog) -> dict:
    """Annotate nodes with cost attributes and return the graph-level estimate."""
    total = Decimal("0.00")
    unpriced_ids: list[str] = []

    for node_id, attrs in graph.nodes(data=True):
        resource_type = attrs["resource_type"]
        calculator = CALCULATORS.get(resource_type)
        if calculator is None:
            result = unpriced(f"no calculator for resource type {resource_type!r}")
        else:
            result = calculator(attrs["configuration"], attrs["usage"], catalog)

        _record(attrs, result)
        total += result.monthly_cost
        if result.status != "priced":
            unpriced_ids.append(node_id)

    summary = {
        "status": "partial" if unpriced_ids else "priced",
        "monthly_cost": str(to_money(total)),
        "currency": catalog.currency,
        "catalog_id": catalog.catalog_id,
        "unpriced_resource_ids": unpriced_ids,
    }
    graph.graph["estimate"] = summary
    # The design file states which catalog it wants; this records the one that
    # actually priced the graph, so the report cannot claim the wrong catalog.
    graph.graph["catalog_id"] = catalog.catalog_id
    return summary


def _record(attrs: dict, result: CostEstimate) -> None:
    # Money is stored as a string so Decimal survives the JSON round-trip
    # (guide section 16.3).
    attrs["monthly_cost"] = str(result.monthly_cost)
    attrs["cost_status"] = result.status
    attrs["cost_breakdown"] = [
        {"name": item.name, "amount": str(item.amount), "unit": item.unit}
        for item in result.breakdown
    ]
    attrs["cost_assumptions"] = list(result.assumptions)
    attrs["cost_missing"] = list(result.missing)
