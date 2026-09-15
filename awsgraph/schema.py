"""Pydantic models. Single source of truth for the .awsgraph.json format."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

AwsRegion = Literal["ap-northeast-2"]
DEFAULT_CATALOG_ID = "ap-northeast-2-2026-09"

RESOURCE_TYPES = frozenset(
    {"vpc", "subnet", "ec2", "ebs", "rds", "alb", "nat-gateway"}
)

Count = Annotated[int, Field(ge=1)]
Hours = Annotated[float, Field(ge=0, le=744)]
MonthFraction = Annotated[float, Field(gt=0, le=1)]
NonNegative = Annotated[float, Field(ge=0)]


class Base(BaseModel):
    # Design files are user input: reject unknown keys instead of silently ignoring them.
    model_config = ConfigDict(extra="forbid")


class ResourceBase(Base):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    region: AwsRegion = "ap-northeast-2"


# --- VPC / Subnet: structural nodes, no cost assigned in v0.1 --------------


class VpcConfiguration(Base):
    cidr_block: str | None = None


class VpcResource(ResourceBase):
    resource_type: Literal["vpc"] = "vpc"
    configuration: VpcConfiguration = VpcConfiguration()


class SubnetConfiguration(Base):
    cidr_block: str | None = None
    availability_zone: str | None = None


class SubnetResource(ResourceBase):
    resource_type: Literal["subnet"] = "subnet"
    configuration: SubnetConfiguration = SubnetConfiguration()


# --- EC2 -------------------------------------------------------------------


class Ec2Configuration(Base):
    instance_type: str = Field(min_length=1)
    operating_system: Literal["linux"] = "linux"
    tenancy: Literal["shared"] = "shared"
    purchase_option: Literal["on-demand"] = "on-demand"


class Ec2Usage(Base):
    instance_count: Count
    hours_per_month: Hours


class Ec2Resource(ResourceBase):
    resource_type: Literal["ec2"] = "ec2"
    configuration: Ec2Configuration
    usage: Ec2Usage


# --- EBS -------------------------------------------------------------------


class EbsConfiguration(Base):
    volume_type: Literal["gp3"] = "gp3"
    size_gib: Annotated[int, Field(ge=1)]


class EbsUsage(Base):
    volume_count: Count
    month_fraction: MonthFraction = 1.0


class EbsResource(ResourceBase):
    resource_type: Literal["ebs"] = "ebs"
    configuration: EbsConfiguration
    usage: EbsUsage


# --- RDS -------------------------------------------------------------------


class RdsConfiguration(Base):
    engine: Literal["mysql", "postgres"]
    instance_class: str = Field(min_length=1)
    multi_az: Literal[False] = False
    storage_type: Literal["gp3"] = "gp3"
    storage_gib: Annotated[int, Field(ge=20)]


class RdsUsage(Base):
    instance_count: Count
    hours_per_month: Hours
    storage_month_fraction: MonthFraction = 1.0


class RdsResource(ResourceBase):
    resource_type: Literal["rds"] = "rds"
    configuration: RdsConfiguration
    usage: RdsUsage


# --- ALB -------------------------------------------------------------------


class AlbConfiguration(Base):
    scheme: Literal["internet-facing", "internal"] = "internet-facing"


class AlbUsage(Base):
    load_balancer_count: Count
    hours_per_month: Hours
    lcu_hours_per_month: NonNegative


class AlbResource(ResourceBase):
    resource_type: Literal["alb"] = "alb"
    configuration: AlbConfiguration = AlbConfiguration()
    usage: AlbUsage


# --- NAT Gateway -----------------------------------------------------------


class NatGatewayConfiguration(Base):
    connectivity_type: Literal["public"] = "public"


class NatGatewayUsage(Base):
    gateway_count: Count
    hours_per_month: Hours
    processed_gb_per_month: NonNegative


class NatGatewayResource(ResourceBase):
    resource_type: Literal["nat-gateway"] = "nat-gateway"
    configuration: NatGatewayConfiguration = NatGatewayConfiguration()
    usage: NatGatewayUsage


AwsResource = Annotated[
    Union[
        VpcResource,
        SubnetResource,
        Ec2Resource,
        EbsResource,
        RdsResource,
        AlbResource,
        NatGatewayResource,
    ],
    Field(discriminator="resource_type"),
]

Relation = Literal["contains", "attached-to", "routes-to", "connects-to"]


class AwsRelationship(Base):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relation: Relation


class ArchitectureMetadata(Base):
    name: str = Field(min_length=1)


class PricingContext(Base):
    region: AwsRegion = "ap-northeast-2"
    currency: Literal["USD"] = "USD"
    catalog_id: str = DEFAULT_CATALOG_ID


class Position(Base):
    x: float
    y: float


class Layout(Base):
    positions: dict[str, Position] = {}


class Architecture(Base):
    schema_version: Literal["0.1"] = "0.1"
    metadata: ArchitectureMetadata
    pricing_context: PricingContext = PricingContext()
    resources: list[AwsResource] = []
    relationships: list[AwsRelationship] = []
    layout: Layout = Layout()
