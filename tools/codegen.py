"""Generate the web assets that must not drift from awsgraph/schema.py.

    python -m tools.codegen            # write the generated files
    python -m tools.codegen --check    # fail if the committed files are stale

awsgraph/schema.py is the single source of truth. Field names, kinds, bounds and
the connection rules are derived from it; the designer imports the result instead
of keeping its own copy.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal, Union, get_args, get_origin

import annotated_types
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from awsgraph.build import SERVICE_NAMES
from awsgraph.schema import (
    DEFAULT_CATALOG_ID,
    Architecture,
    AwsResource,
)
from awsgraph.validate import CONNECTION_RULES

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_JSON = ROOT / "awsgraph" / "assets" / "schema.json"
RESOURCE_SPEC = ROOT / "webui" / "src" / "generated" / "resource-spec.json"

# Starting values the designer puts on a newly dropped resource. The schema has
# no default for these on purpose -- a design file must state its own usage
# assumptions -- so the seed lives here, next to the schema it belongs to.
SEEDS: dict[tuple[str, str, str], object] = {
    ("vpc", "configuration", "cidr_block"): "10.0.0.0/16",
    ("subnet", "configuration", "cidr_block"): "10.0.1.0/24",
    ("subnet", "configuration", "availability_zone"): "ap-northeast-2a",
    ("ec2", "configuration", "instance_type"): "t3.medium",
    ("ec2", "usage", "instance_count"): 1,
    ("ec2", "usage", "hours_per_month"): 730,
    ("ebs", "configuration", "size_gib"): 100,
    ("ebs", "usage", "volume_count"): 1,
    ("rds", "configuration", "engine"): "postgres",
    ("rds", "configuration", "instance_class"): "db.t3.medium",
    ("rds", "configuration", "storage_gib"): 100,
    ("rds", "usage", "instance_count"): 1,
    ("rds", "usage", "hours_per_month"): 730,
    ("alb", "usage", "load_balancer_count"): 1,
    ("alb", "usage", "hours_per_month"): 730,
    ("alb", "usage", "lcu_hours_per_month"): 0,
    ("nat-gateway", "usage", "gateway_count"): 1,
    ("nat-gateway", "usage", "hours_per_month"): 730,
    ("nat-gateway", "usage", "processed_gb_per_month"): 0,
}

# Words that lose meaning when naively title-cased.
WORDS = {"gib": "GiB", "gb": "GB", "lcu": "LCU", "cidr": "CIDR", "az": "AZ", "id": "ID"}


def humanize(key: str) -> str:
    parts = [WORDS.get(part, part) for part in key.split("_")]
    first, *rest = parts
    return " ".join([first if first in WORDS.values() else first.capitalize(), *rest])


def _unwrap_optional(annotation: object) -> tuple[object, bool]:
    origin = get_origin(annotation)
    if origin is Union or str(origin) == "<class 'types.UnionType'>":
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return annotation, False


def describe_field(
    resource_type: str, group: str, name: str, field: object
) -> tuple[dict | None, object]:
    """Return (ui field spec or None if fixed, default value for the designer)."""
    annotation, optional = _unwrap_optional(field.annotation)  # type: ignore[attr-defined]
    options: list[str] | None = None
    if get_origin(annotation) is Literal:
        options = [str(a) for a in get_args(annotation)]

    seed = SEEDS.get((resource_type, group, name), PydanticUndefined)
    default = seed if seed is not PydanticUndefined else field.default  # type: ignore[attr-defined]
    if default is PydanticUndefined:
        raise SystemExit(
            f"{resource_type}.{group}.{name} is required but has no seed value. "
            f"Add it to SEEDS in tools/codegen.py."
        )

    # A Literal with one option is not a choice; the designer must not show it.
    if options is not None and len(options) == 1:
        return None, default

    spec: dict[str, object] = {"key": name, "group": group, "label": humanize(name)}
    if options is not None:
        spec["kind"] = "select"
        spec["options"] = options
    elif annotation in (int, float):
        spec["kind"] = "number"
        spec["step"] = 1 if annotation is int else "any"
    else:
        spec["kind"] = "text"
    if optional:
        spec["optional"] = True

    for constraint in getattr(field, "metadata", []):
        if isinstance(constraint, annotated_types.Ge):
            spec["min"] = constraint.ge
        elif isinstance(constraint, annotated_types.Gt):
            spec["min"] = constraint.gt
        elif isinstance(constraint, annotated_types.Le):
            spec["max"] = constraint.le

    return spec, default


def resource_models() -> dict[str, type[BaseModel]]:
    models = {}
    for model in get_args(get_args(AwsResource)[0]):
        resource_type = model.model_fields["resource_type"].default
        models[resource_type] = model
    return models


def build_resource_spec() -> dict:
    resources: dict[str, dict] = {}
    for resource_type, model in resource_models().items():
        entry: dict[str, object] = {
            "label": SERVICE_NAMES[resource_type],
            "service": SERVICE_NAMES[resource_type],
            "configuration": {},
            "fields": [],
        }
        for group in ("configuration", "usage"):
            field = model.model_fields.get(group)
            if field is None:
                continue
            group_model, _ = _unwrap_optional(field.annotation)
            defaults: dict[str, object] = {}
            for name, sub in group_model.model_fields.items():  # type: ignore[union-attr]
                spec, default = describe_field(resource_type, group, name, sub)
                defaults[name] = default
                if spec is not None:
                    entry["fields"].append(spec)  # type: ignore[union-attr]
            entry[group] = defaults
        resources[resource_type] = entry

    return {
        "comment": "GENERATED by tools/codegen.py from awsgraph/schema.py. Do not edit.",
        "schema_version": "0.1",
        "region": "ap-northeast-2",
        "default_catalog_id": DEFAULT_CATALOG_ID,
        "resource_order": list(resources),
        "resources": resources,
        "connection_rules": {
            f"{source}>{target}": sorted(relations)
            for (source, target), relations in sorted(CONNECTION_RULES.items())
        },
    }


def outputs() -> dict[Path, str]:
    return {
        SCHEMA_JSON: json.dumps(Architecture.model_json_schema(), indent=2) + "\n",
        RESOURCE_SPEC: json.dumps(build_resource_spec(), indent=2) + "\n",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if a file is stale")
    args = parser.parse_args(argv)

    stale = []
    for path, content in outputs().items():
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current != content:
                stale.append(path.relative_to(ROOT))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")

    if stale:
        for path in stale:
            print(f"{path} is stale.", file=sys.stderr)
        print("Run `python -m tools.codegen` and commit the result.", file=sys.stderr)
        return 1
    if args.check:
        print("Generated files are up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
