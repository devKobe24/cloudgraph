export type ResourceType = "vpc" | "subnet" | "ec2" | "ebs" | "rds" | "alb" | "nat-gateway";

export type Relation = "contains" | "attached-to" | "routes-to" | "connects-to";

export interface AwsResource {
  id: string;
  name: string;
  region: string;
  resource_type: ResourceType;
  configuration: Record<string, unknown>;
  usage?: Record<string, unknown>;
}

export interface AwsRelationship {
  id: string;
  source: string;
  target: string;
  relation: Relation;
}

export interface Architecture {
  schema_version: "0.1";
  metadata: { name: string };
  pricing_context: { region: string; currency: string; catalog_id: string };
  resources: AwsResource[];
  relationships: AwsRelationship[];
  layout: { positions: Record<string, { x: number; y: number }> };
}

export interface PricingCatalog {
  catalog_id: string;
  region: string;
  currency: string;
  rates: Record<string, string>;
}

export interface CostEstimate {
  status: "priced" | "partial" | "unpriced";
  cents: bigint;
  breakdown: { name: string; cents: bigint }[];
  missing: string[];
}
