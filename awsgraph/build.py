"""Architecture model -> nx.MultiDiGraph. No pricing here (guide section 7.1)."""

from __future__ import annotations

import networkx as nx

from . import __version__
from .schema import Architecture

SERVICE_NAMES = {
    "vpc": "VPC",
    "subnet": "Subnet",
    "ec2": "EC2",
    "ebs": "EBS",
    "rds": "RDS",
    "alb": "ALB",
    "nat-gateway": "NAT Gateway",
}


def build(architecture: Architecture) -> nx.MultiDiGraph:
    # MultiDiGraph, not DiGraph: two resources may be joined by more than one
    # relation and a plain DiGraph would collapse them (guide section 11.1).
    graph = nx.MultiDiGraph()
    graph.graph.update(
        schema_version=architecture.schema_version,
        product_version=__version__,
        architecture_name=architecture.metadata.name,
        region=architecture.pricing_context.region,
        currency=architecture.pricing_context.currency,
        catalog_id=architecture.pricing_context.catalog_id,
    )

    for resource in architecture.resources:
        usage = getattr(resource, "usage", None)
        graph.add_node(
            resource.id,
            label=resource.name,
            resource_type=resource.resource_type,
            service=SERVICE_NAMES[resource.resource_type],
            region=resource.region,
            configuration=resource.configuration.model_dump(),
            usage=usage.model_dump() if usage is not None else {},
            # v0.1 nodes are user-declared; the v0.2 scanner writes kind="discovered".
            provenance={"kind": "declared"},
        )

    for relationship in architecture.relationships:
        graph.add_edge(
            relationship.source,
            relationship.target,
            key=relationship.id,
            id=relationship.id,
            relation=relationship.relation,
            provenance={"kind": "declared"},
        )

    _check_invariants(graph, architecture)
    return graph


def _check_invariants(graph: nx.MultiDiGraph, architecture: Architecture) -> None:
    """Guard against silent collapse: networkx overwrites duplicate ids without complaint."""
    if graph.number_of_nodes() != len(architecture.resources):
        raise ValueError(
            f"build produced {graph.number_of_nodes()} nodes "
            f"for {len(architecture.resources)} resources (duplicate resource ids?)"
        )
    if graph.number_of_edges() != len(architecture.relationships):
        raise ValueError(
            f"build produced {graph.number_of_edges()} edges "
            f"for {len(architecture.relationships)} relationships (duplicate relationship ids?)"
        )
