// Everything here comes from awsgraph/schema.py via tools/codegen.py.
// Do not hand-maintain resource fields or connection rules: CI runs
// `python -m tools.codegen --check` and fails if this file's input is stale.

import generated from "./generated/resource-spec.json";
import type { AwsResource, Relation, ResourceType } from "./types";

export interface FieldSpec {
  key: string;
  label: string;
  group: "configuration" | "usage";
  kind: "number" | "text" | "select";
  options?: string[];
  min?: number;
  max?: number;
  step?: number | "any";
  optional?: boolean;
}

export interface ResourceSpec {
  type: ResourceType;
  label: string;
  service: string;
  configuration: Record<string, unknown>;
  usage?: Record<string, unknown>;
  fields: FieldSpec[];
}

type GeneratedResource = {
  label: string;
  service: string;
  configuration: Record<string, unknown>;
  usage?: Record<string, unknown>;
  fields: FieldSpec[];
};

const RESOURCES = generated.resources as unknown as Record<ResourceType, GeneratedResource>;

export const REGION: string = generated.region;
export const DEFAULT_CATALOG_ID: string = generated.default_catalog_id;
export const RESOURCE_ORDER = generated.resource_order as ResourceType[];

export const RESOURCE_SPECS = Object.fromEntries(
  RESOURCE_ORDER.map((type) => [type, { type, ...RESOURCES[type] }]),
) as Record<ResourceType, ResourceSpec>;

const RULES = generated.connection_rules as unknown as Record<string, Relation[]>;

export function allowedRelations(source: ResourceType, target: ResourceType): Relation[] {
  return RULES[`${source}>${target}`] ?? [];
}

/**
 * Fill in schema defaults the way Pydantic does when Python loads a design file.
 * An imported .awsgraph.json may omit every field that has a default, and a
 * half-filled resource would price against keys like "ec2/undefined/...".
 */
export function withDefaults(resource: AwsResource): AwsResource {
  const spec = RESOURCE_SPECS[resource.resource_type];
  if (!spec) return resource;
  return {
    ...resource,
    region: resource.region ?? REGION,
    configuration: { ...spec.configuration, ...(resource.configuration ?? {}) },
    usage: spec.usage ? { ...spec.usage, ...(resource.usage ?? {}) } : resource.usage,
  };
}
