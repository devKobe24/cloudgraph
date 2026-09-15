import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { componentCents, formatCents } from "./money";
import { estimateResource } from "./pricing";
import type { AwsResource, PricingCatalog } from "./types";

interface Case {
  name: string;
  resource: AwsResource;
  expected_monthly_cost: string;
  expected_status: string;
}

const fixture = JSON.parse(
  readFileSync(new URL("../../tests/fixtures/pricing_cases.json", import.meta.url), "utf-8"),
) as { catalog: PricingCatalog; cases: Case[] };

describe("parity with the Python estimator", () => {
  for (const testCase of fixture.cases) {
    it(testCase.name, () => {
      const result = estimateResource(testCase.resource, fixture.catalog);
      expect(formatCents(result.cents)).toBe(testCase.expected_monthly_cost);
      expect(result.status).toBe(testCase.expected_status);
    });
  }
});

describe("decimal arithmetic", () => {
  it("rounds a half cent up the way Decimal does", () => {
    // 0.0225 * 730 is exactly 16.425; float would give 16.42.
    expect(formatCents(componentCents("0.0225", [730]))).toBe("16.43");
  });

  it("does not drift on repeated fractional rates", () => {
    expect(formatCents(componentCents("0.0912", [100, 1, 0.5]))).toBe("4.56");
  });

  it("formats whole amounts with two decimals", () => {
    expect(formatCents(0n)).toBe("0.00");
    expect(formatCents(700n)).toBe("7.00");
  });
});
