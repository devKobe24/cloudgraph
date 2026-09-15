"""Semantic and referential validation. Pydantic covers field shape; this covers the graph."""

from __future__ import annotations

from .schema import Architecture

# (source type, target type) -> allowed relations.
# A subnet both *contains* the NAT gateway it hosts and *routes-to* the one it
# egresses through, so that pair allows two relations.
CONNECTION_RULES: dict[tuple[str, str], set[str]] = {
    ("vpc", "subnet"): {"contains"},
    ("subnet", "ec2"): {"contains"},
    ("subnet", "rds"): {"contains"},
    ("subnet", "alb"): {"contains"},
    ("subnet", "nat-gateway"): {"contains", "routes-to"},
    ("ec2", "ebs"): {"attached-to"},
    ("alb", "ec2"): {"connects-to"},
    ("ec2", "rds"): {"connects-to"},
}


def validate_design(architecture: Architecture) -> list[str]:
    """Return every problem found. Empty list means the design is valid."""
    errors: list[str] = []

    resource_types: dict[str, str] = {}
    for i, resource in enumerate(architecture.resources):
        if resource.id in resource_types:
            errors.append(f"resources[{i}].id: duplicate resource id {resource.id!r}")
            continue
        resource_types[resource.id] = resource.resource_type

    seen_edge_ids: set[str] = set()
    seen_triples: set[tuple[str, str, str]] = set()
    for i, rel in enumerate(architecture.relationships):
        where = f"relationships[{i}]"
        if rel.id in seen_edge_ids:
            errors.append(f"{where}.id: duplicate relationship id {rel.id!r}")
        seen_edge_ids.add(rel.id)

        missing = False
        for field in ("source", "target"):
            ref = getattr(rel, field)
            if ref not in resource_types:
                errors.append(f"{where}.{field}: unknown resource id {ref!r}")
                missing = True
        if missing:
            continue

        if rel.source == rel.target:
            errors.append(f"{where}: self-loop on {rel.source!r} is not allowed")
            continue

        triple = (rel.source, rel.target, rel.relation)
        if triple in seen_triples:
            errors.append(
                f"{where}: duplicate {rel.relation!r} relationship "
                f"from {rel.source!r} to {rel.target!r}"
            )
        seen_triples.add(triple)

        source_type = resource_types[rel.source]
        target_type = resource_types[rel.target]
        allowed = CONNECTION_RULES.get((source_type, target_type))
        if allowed is None:
            errors.append(
                f"{where}.relation: no relationship is allowed "
                f"from {source_type} to {target_type}"
            )
        elif rel.relation not in allowed:
            errors.append(
                f"{where}.relation: {rel.relation!r} is not allowed "
                f"from {source_type} to {target_type} "
                f"(allowed: {', '.join(sorted(allowed))})"
            )

    return errors
