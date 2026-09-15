import { placeMissing } from "./layout";
import { DEFAULT_CATALOG_ID, REGION, RESOURCE_SPECS, withDefaults } from "./spec";
import type { Architecture, AwsResource, PricingCatalog, ResourceType } from "./types";

const DATA_ELEMENT = "awsgraph-design";
const UNREPLACED = "__AWSGRAPH_DESIGN__";

export function newId(prefix: "res" | "edge"): string {
  const uuid =
    typeof crypto?.randomUUID === "function"
      ? crypto.randomUUID().replace(/-/g, "")
      : Math.random().toString(16).slice(2) + Date.now().toString(16);
  return `${prefix}_${uuid}`;
}

export function emptyArchitecture(): Architecture {
  return {
    schema_version: "0.1",
    metadata: { name: "My AWS Architecture" },
    pricing_context: { region: REGION, currency: "USD", catalog_id: DEFAULT_CATALOG_ID },
    resources: [],
    relationships: [],
    layout: { positions: {} },
  };
}

const EMPTY_CATALOG: PricingCatalog = {
  catalog_id: "none",
  region: REGION,
  currency: "USD",
  rates: {},
};

/** Read what `awsgraph design` embedded, or start empty when opened directly. */
export function readInjected(): { architecture: Architecture; catalog: PricingCatalog } {
  const element = document.getElementById(DATA_ELEMENT);
  const raw = element?.textContent?.trim();
  if (!raw || raw === UNREPLACED) {
    return { architecture: emptyArchitecture(), catalog: EMPTY_CATALOG };
  }
  try {
    const payload = JSON.parse(raw);
    return {
      architecture: normalize(payload.architecture),
      catalog: payload.catalog ?? EMPTY_CATALOG,
    };
  } catch {
    return { architecture: emptyArchitecture(), catalog: EMPTY_CATALOG };
  }
}

export function normalize(input: Partial<Architecture> | undefined): Architecture {
  const base = emptyArchitecture();
  if (!input) return base;
  const architecture: Architecture = {
    ...base,
    ...input,
    metadata: { ...base.metadata, ...(input.metadata ?? {}) },
    pricing_context: { ...base.pricing_context, ...(input.pricing_context ?? {}) },
    resources: (input.resources ?? []).map(withDefaults),
    relationships: input.relationships ?? [],
    layout: { positions: input.layout?.positions ?? {} },
  };
  return { ...architecture, layout: { positions: placeMissing(architecture) } };
}

export function createResource(type: ResourceType, index: number): AwsResource {
  const spec = RESOURCE_SPECS[type];
  return withDefaults({
    id: newId("res"),
    name: `${spec.label} ${index}`,
    region: REGION,
    resource_type: type,
    configuration: { ...spec.configuration },
    usage: spec.usage ? { ...spec.usage } : undefined,
  });
}

/** Serialize for export. Undefined keys drop out, which matters because the
 *  Python schema forbids unknown fields (a VPC must not carry `usage`). */
export function serialize(architecture: Architecture): string {
  const known = new Set(architecture.resources.map((r) => r.id));
  const positions = Object.fromEntries(
    Object.entries(architecture.layout.positions).filter(([id]) => known.has(id)),
  );
  return JSON.stringify({ ...architecture, layout: { positions } }, null, 2) + "\n";
}

export function download(architecture: Architecture): void {
  const blob = new Blob([serialize(architecture)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${architecture.metadata.name.replace(/\W+/g, "-").toLowerCase()}.awsgraph.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
