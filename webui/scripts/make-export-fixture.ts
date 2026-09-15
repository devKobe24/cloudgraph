// Builds tests/fixtures/designer-export.awsgraph.json: what the designer writes
// when every resource type is placed and every allowed relation drawn. Python
// validates the same file, so the two schemas cannot drift apart silently.
//
//   npx vite-node scripts/make-export-fixture.ts

import { writeFileSync } from "node:fs";

import { createResource, emptyArchitecture, serialize } from "../src/io";
import { allowedRelations, RESOURCE_ORDER } from "../src/spec";
import type { Architecture, Relation } from "../src/types";

export function buildExportFixture(): Architecture {
  const architecture = emptyArchitecture();
  architecture.metadata.name = "Designer Export";

  RESOURCE_ORDER.forEach((type, index) => {
    const resource = createResource(type, 1);
    resource.id = `res_${type.replace("-", "_")}`;
    architecture.resources.push(resource);
    architecture.layout.positions[resource.id] = {
      x: (index % 3) * 210,
      y: Math.floor(index / 3) * 130,
    };
  });

  for (const source of architecture.resources) {
    for (const target of architecture.resources) {
      for (const relation of allowedRelations(source.resource_type, target.resource_type)) {
        architecture.relationships.push({
          id: `edge_${source.resource_type}_${target.resource_type}_${relation}`.replace(/-/g, "_"),
          source: source.id,
          target: target.id,
          relation: relation as Relation,
        });
      }
    }
  }
  return architecture;
}

export const FIXTURE_URL = new URL(
  "../../tests/fixtures/designer-export.awsgraph.json",
  import.meta.url,
);

if (import.meta.url === `file://${process.argv[1]}`) {
  const architecture = buildExportFixture();
  writeFileSync(FIXTURE_URL, serialize(architecture));
  console.log(
    `${architecture.resources.length} resources, ${architecture.relationships.length} relationships`,
  );
}
