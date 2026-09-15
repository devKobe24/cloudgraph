# File format

Two files, and they are not the same thing.

| File | Role | Written by |
|---|---|---|
| `*.awsgraph.json` | editable source of truth | you, or the designer |
| `awsgraph-out/graph.json` | derived query artifact | `awsgraph build` |

The design file holds intent: resources, usage assumptions, relationships,
layout. It never holds computed costs. Everything derived lives in `graph.json`,
which every query command reads. Delete `awsgraph-out/` and nothing is lost.

## Design file

```json
{
  "schema_version": "0.1",
  "metadata": { "name": "Three Tier" },
  "pricing_context": {
    "region": "ap-northeast-2",
    "currency": "USD",
    "catalog_id": "ap-northeast-2-2026-09"
  },
  "resources": [
    {
      "id": "res_ec2",
      "name": "Backend EC2",
      "resource_type": "ec2",
      "configuration": { "instance_type": "t3.medium" },
      "usage": { "instance_count": 2, "hours_per_month": 730 }
    }
  ],
  "relationships": [
    { "id": "edge_1", "source": "res_alb", "target": "res_ec2", "relation": "connects-to" }
  ],
  "layout": { "positions": { "res_ec2": { "x": 0, "y": 240 } } }
}
```

`awsgraph/assets/schema.json` is the JSON Schema for this file, generated from
`awsgraph/schema.py`. Point an editor at it for completion and inline errors.

Unknown keys are rejected. A typo is a validation error, not a silently ignored
field.

`id` is stable and independent of `name`: rename freely, references hold.

`usage` exists only on resources that cost money. A VPC or Subnet carrying a
`usage` object fails validation.

## Relationships

Four relations, and direction is part of the meaning.

| Relation | source | target |
|---|---|---|
| `contains` | container | contained resource |
| `attached-to` | attached resource | attachment target |
| `routes-to` | traffic source | route target |
| `connects-to` | caller | dependency |

Only these pairs are allowed:

| source → target | relations |
|---|---|
| vpc → subnet | contains |
| subnet → ec2 / rds / alb | contains |
| subnet → nat-gateway | contains, routes-to |
| ec2 → ebs | attached-to |
| alb → ec2 | connects-to |
| ec2 → rds | connects-to |

Two resources may be joined by more than one relation — a public subnet both
contains a NAT gateway and may route through it. That is why the graph is a
`MultiDiGraph` and why `graph.json` carries `"multigraph": true`.

## graph.json

NetworkX node-link data plus `awsgraph_schema_version`. Edge `key` is the
relationship id, so parallel edges survive a round trip.

Money is stored as a **string** (`"75.92"`), never a JSON number, so the decimal
value survives serialization unchanged.

## Four versions, kept apart

| Field | Means |
|---|---|
| `schema_version` | the design file format |
| `awsgraph_schema_version` | the `graph.json` wrapper |
| `product_version` | the AWSGraph release |
| `catalog_id` | which pricing data produced the numbers |

They move independently. Do not collapse them into one string.
