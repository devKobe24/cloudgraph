import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { buildExportFixture, FIXTURE_URL } from "../scripts/make-export-fixture";
import { createResource, serialize } from "../src/io";
import { RESOURCE_ORDER } from "../src/spec";

describe("designer export", () => {
  it("still matches the fixture Python validates", () => {
    // If this fails the designer changed what it writes. Regenerate with
    // `npx vite-node scripts/make-export-fixture.ts` and re-run the Python tests.
    expect(serialize(buildExportFixture())).toBe(readFileSync(FIXTURE_URL, "utf-8"));
  });

  it("omits usage on resources whose Python schema has no usage field", () => {
    // Architecture has extra="forbid": an empty usage object would be rejected.
    for (const type of ["vpc", "subnet"] as const) {
      const json = JSON.parse(serialize({
        ...buildExportFixture(),
        resources: [createResource(type, 1)],
        relationships: [],
        layout: { positions: {} },
      }));
      expect(json.resources[0]).not.toHaveProperty("usage");
    }
  });

  it("writes usage for every priced resource type", () => {
    for (const type of RESOURCE_ORDER) {
      if (type === "vpc" || type === "subnet") continue;
      expect(createResource(type, 1).usage).toBeDefined();
    }
  });
});
