// Preview estimator. The Python estimator in awsgraph/pricing.py is the reference
// implementation; this mirrors it for live feedback in the designer. Both run the
// cases in tests/fixtures/pricing_cases.json, and CI fails if they disagree.

import { componentCents } from "./money";
import { withDefaults } from "./spec";
import type { AwsResource, CostEstimate, PricingCatalog, ResourceType } from "./types";

type Component = [label: string, key: string, factors: (number | string)[]];

function compose(catalog: PricingCatalog, components: Component[]): CostEstimate {
  const breakdown: { name: string; cents: bigint }[] = [];
  const missing: string[] = [];
  let cents = 0n;

  for (const [label, key, factors] of components) {
    const rate = catalog.rates[key];
    if (rate === undefined) {
      missing.push(`missing price: ${key}`);
      continue;
    }
    const amount = componentCents(rate, factors);
    breakdown.push({ name: label, cents: amount });
    cents += amount;
  }

  const status = breakdown.length === 0 ? "unpriced" : missing.length > 0 ? "partial" : "priced";
  return { status, cents, breakdown, missing };
}

const num = (value: unknown, fallback = 0): number =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;

const CALCULATORS: Record<ResourceType, (r: AwsResource, c: PricingCatalog) => CostEstimate> = {
  vpc: (_r, _c) => ({ status: "priced", cents: 0n, breakdown: [], missing: [] }),
  subnet: (_r, _c) => ({ status: "priced", cents: 0n, breakdown: [], missing: [] }),

  ec2: (resource, catalog) => {
    const config = resource.configuration;
    const usage = resource.usage ?? {};
    const key = `ec2/${config.operating_system}/${config.tenancy}/${config.purchase_option}/${config.instance_type}`;
    return compose(catalog, [
      ["instance hours", key, [num(usage.hours_per_month), num(usage.instance_count, 1)]],
    ]);
  },

  ebs: (resource, catalog) => {
    const config = resource.configuration;
    const usage = resource.usage ?? {};
    return compose(catalog, [
      [
        "provisioned storage",
        `ebs/${config.volume_type}/gb-month`,
        [num(config.size_gib), num(usage.volume_count, 1), num(usage.month_fraction, 1)],
      ],
    ]);
  },

  rds: (resource, catalog) => {
    const config = resource.configuration;
    const usage = resource.usage ?? {};
    return compose(catalog, [
      [
        "instance hours",
        `rds/${config.engine}/single-az/on-demand/${config.instance_class}`,
        [num(usage.hours_per_month), num(usage.instance_count, 1)],
      ],
      [
        "storage",
        `rds/storage/${config.storage_type}/gb-month`,
        [
          num(config.storage_gib),
          num(usage.instance_count, 1),
          num(usage.storage_month_fraction, 1),
        ],
      ],
    ]);
  },

  alb: (resource, catalog) => {
    const usage = resource.usage ?? {};
    return compose(catalog, [
      [
        "load balancer hours",
        "alb/load-balancer-hour",
        [num(usage.hours_per_month), num(usage.load_balancer_count, 1)],
      ],
      ["LCU hours", "alb/lcu-hour", [num(usage.lcu_hours_per_month)]],
    ]);
  },

  "nat-gateway": (resource, catalog) => {
    const usage = resource.usage ?? {};
    return compose(catalog, [
      [
        "gateway hours",
        "nat-gateway/gateway-hour",
        [num(usage.hours_per_month), num(usage.gateway_count, 1)],
      ],
      ["data processing", "nat-gateway/processed-gb", [num(usage.processed_gb_per_month)]],
    ]);
  },
};

export function estimateResource(input: AwsResource, catalog: PricingCatalog): CostEstimate {
  const calculator = CALCULATORS[input.resource_type];
  if (!calculator) {
    return {
      status: "unpriced",
      cents: 0n,
      breakdown: [],
      missing: [`missing price: no calculator for resource type '${input.resource_type}'`],
    };
  }
  return calculator(withDefaults(input), catalog);
}

export function estimateAll(
  resources: AwsResource[],
  catalog: PricingCatalog,
): { total: bigint; byId: Map<string, CostEstimate> } {
  const byId = new Map<string, CostEstimate>();
  let total = 0n;
  for (const resource of resources) {
    const estimate = estimateResource(resource, catalog);
    byId.set(resource.id, estimate);
    total += estimate.cents;
  }
  return { total, byId };
}
