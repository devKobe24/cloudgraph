# Pricing

## Where the numbers come from

`awsgraph/data/pricing/ap-northeast-2.json`. A local, versioned file. Nothing in
`awsgraph build` calls the network, so an estimate is reproducible offline and
identical on every machine holding the same catalog.

**The rates are entered by hand and approximate.** They are AWS on-demand list
prices for `ap-northeast-2` as understood by a maintainer, not a feed from the
Price List API. `tools/update_pricing.py` does not exist yet; until it does,
treat the totals as an order-of-magnitude answer to "which resource dominates
this design", not as a bill.

## Catalog format

```json
{
  "catalog_id": "ap-northeast-2-2026-09",
  "region": "ap-northeast-2",
  "currency": "USD",
  "rates": { "ec2/linux/shared/on-demand/t3.medium": "0.0520" }
}
```

Rates are decimal **strings**, never JSON numbers: `0.0520` as a float cannot be
represented exactly and the arithmetic has to stay exact.

A design file names the catalog it expects in `pricing_context.catalog_id`. If
the bundled catalog has a different id, `awsgraph build` fails rather than
pricing against something the design did not ask for.

## How a resource is priced

| Service | Formula |
|---|---|
| EC2 | `rate x hours_per_month x instance_count` |
| EBS (gp3) | `rate x size_gib x volume_count x month_fraction` |
| RDS (Single-AZ) | `compute_rate x hours x count` + `storage_rate x storage_gib x count x fraction` |
| ALB | `lb_rate x hours x count` + `lcu_rate x lcu_hours_per_month` |
| NAT Gateway | `gw_rate x hours x count` + `gb_rate x processed_gb_per_month` |
| VPC, Subnet | `0` |

VPC and Subnet at zero does **not** mean VPCs are free. It means v0.1 assigns no
cost to those nodes themselves.

## Missing rates are never zero

A lookup returns `None`, not a default. The resource comes back as:

- `unpriced` — no component could be priced
- `partial` — some components priced, others missing (an RDS whose instance
  class is absent but whose storage rate is known)

Both appear in `AWS_REPORT.md`, in `awsgraph estimate`, and as a dashed border in
the viewer. A quietly cheap total is worse than an obviously incomplete one.

## Rounding

Every component rounds to cents once, with `ROUND_HALF_UP`, then the components
sum. The graph total is therefore exactly the sum of the node costs.

The designer's live preview is a second implementation in TypeScript. Float
arithmetic there would disagree with Python (`0.0225 x 730` is `16.424999...` in
JS and rounds down), so it uses BigInt at a fixed scale.
`tests/fixtures/pricing_cases.json` runs the same cases through both and CI fails
if they diverge.

## Not modelled in v0.1

Public IPv4 addresses, data transfer that is not explicitly modelled, snapshots
and backup beyond provisioned storage, taxes, credits, Savings Plans, Reserved
Instances, Spot, and the free tier. Every report repeats this list.
