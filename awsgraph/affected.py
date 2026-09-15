"""Impact traversal.

Not a plain reverse BFS: which way a change propagates depends on the relation
(guide section 21.5). A caller depends on its callee, but a container's contents
depend on the container.
"""

from __future__ import annotations

import networkx as nx

# Direction to walk from the changed resource to find what it affects.
AFFECTED_POLICY = {
    "connects-to": "incoming",  # whoever connects to me depends on me
    "attached-to": "incoming",  # whoever attached me depends on me
    "routes-to": "incoming",  # whoever routes through me depends on me
    "contains": "outgoing",  # what I contain depends on me
}


def affected(graph: nx.MultiDiGraph, start: str, depth: int | None = None) -> list[dict]:
    """Breadth-first walk outward from `start`, one entry per reached resource."""
    seen = {start}
    frontier = [start]
    results: list[dict] = []
    level = 0

    while frontier and (depth is None or level < depth):
        level += 1
        discovered: dict[str, set[str]] = {}

        for node_id in frontier:
            for source, _, attrs in graph.in_edges(node_id, data=True):
                if AFFECTED_POLICY.get(attrs["relation"]) == "incoming":
                    _note(discovered, seen, source, attrs["relation"])
            for _, target, attrs in graph.out_edges(node_id, data=True):
                if AFFECTED_POLICY.get(attrs["relation"]) == "outgoing":
                    _note(discovered, seen, target, attrs["relation"])

        # Mark after the whole level so parallel edges cannot emit a node twice.
        seen.update(discovered)
        for node_id in sorted(discovered, key=lambda n: graph.nodes[n]["label"]):
            results.append(
                {
                    "id": node_id,
                    "label": graph.nodes[node_id]["label"],
                    "service": graph.nodes[node_id]["service"],
                    "depth": level,
                    "via": sorted(discovered[node_id]),
                }
            )
        frontier = list(discovered)

    return results


def _note(discovered: dict[str, set[str]], seen: set[str], node_id: str, relation: str) -> None:
    if node_id in seen:
        return
    discovered.setdefault(node_id, set()).add(relation)


def render_affected(graph: nx.MultiDiGraph, start: str, depth: int | None = None) -> str:
    hits = affected(graph, start, depth)
    label = graph.nodes[start]["label"]
    if not hits:
        return f"Nothing depends on {label}."

    lines = [f"Affected by a change to {label}:", ""]
    current = 0
    for item in hits:
        if item["depth"] != current:
            current = item["depth"]
            lines.append(f"depth {current}:")
        lines.append(f"  {item['label']} ({item['service']}) [{', '.join(item['via'])}]")
    return "\n".join(lines)
