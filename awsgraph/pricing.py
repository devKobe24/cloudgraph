"""Pricing catalog and per-resource calculators.

Rules that do not bend (guide sections 13.1 / 13.9):
- no network calls, ever; the catalog is a local versioned file
- money is Decimal, never float
- a missing rate returns status "unpriced", never a silent 0
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from importlib import resources
from pathlib import Path

CENT = Decimal("0.01")


def to_money(value: Decimal) -> Decimal:
    """Round to cents. Node costs are rounded here so the graph total is an exact sum."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CostItem:
    name: str
    amount: Decimal
    unit: str | None = None


@dataclass(frozen=True)
class CostEstimate:
    status: str  # priced | unpriced | partial
    monthly_cost: Decimal
    breakdown: tuple[CostItem, ...] = ()
    assumptions: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


def unpriced(*keys: str) -> CostEstimate:
    return CostEstimate(
        status="unpriced",
        monthly_cost=Decimal("0"),
        missing=tuple(f"missing price: {key}" for key in keys),
    )


class CatalogError(Exception):
    pass


@dataclass(frozen=True)
class PricingCatalog:
    catalog_id: str
    region: str
    currency: str
    rates: Mapping[str, str]

    def lookup(self, key: str) -> Decimal | None:
        """Return the rate, or None. Never a default — see guide section 13.9."""
        raw = self.rates.get(key)
        return None if raw is None else Decimal(raw)

    @classmethod
    def from_mapping(cls, data: Mapping[str, object], source: str) -> PricingCatalog:
        missing = [k for k in ("catalog_id", "region", "currency", "rates") if k not in data]
        if missing:
            raise CatalogError(f"{source}: catalog is missing {', '.join(missing)}")
        return cls(
            catalog_id=str(data["catalog_id"]),
            region=str(data["region"]),
            currency=str(data["currency"]),
            rates=dict(data["rates"]),  # type: ignore[arg-type]
        )

    @classmethod
    def from_file(cls, path: str | Path) -> PricingCatalog:
        p = Path(path)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError(f"{p}: {exc}") from exc
        return cls.from_mapping(data, str(p))


def load_catalog(region: str, catalog_id: str | None = None) -> PricingCatalog:
    """Load the catalog shipped with the package for one region."""
    resource = resources.files("awsgraph") / "data" / "pricing" / f"{region}.json"
    if not resource.is_file():
        raise CatalogError(f"no pricing catalog bundled for region {region!r}")
    catalog = PricingCatalog.from_mapping(
        json.loads(resource.read_text(encoding="utf-8")), f"{region}.json"
    )
    if catalog_id is not None and catalog.catalog_id != catalog_id:
        raise CatalogError(
            f"design file asks for catalog {catalog_id!r} but the bundled catalog "
            f"for {region} is {catalog.catalog_id!r}"
        )
    return catalog


# --- calculators -----------------------------------------------------------
# Every calculator takes (configuration, usage, catalog) so the registry stays flat.
# Each one declares its cost components and lets _compose do the lookups, so a
# half-priced resource reports status "partial" instead of a quietly low number.


def _compose(
    catalog: PricingCatalog,
    components: Iterable[tuple[str, str, Decimal]],
    assumptions: Iterable[str] = (),
) -> CostEstimate:
    items: list[CostItem] = []
    missing: list[str] = []
    total = Decimal("0.00")

    for label, key, quantity in components:
        rate = catalog.lookup(key)
        if rate is None:
            missing.append(f"missing price: {key}")
            continue
        amount = to_money(rate * quantity)
        items.append(CostItem(label, amount, catalog.currency))
        total += amount

    if not items:
        status = "unpriced"
    elif missing:
        status = "partial"
    else:
        status = "priced"

    return CostEstimate(
        status=status,
        monthly_cost=total,
        breakdown=tuple(items),
        assumptions=tuple(assumptions),
        missing=tuple(missing),
    )


def _q(value: object) -> Decimal:
    """Quantity as Decimal. Goes through str so float usage values do not drift."""
    return Decimal(str(value))


def calculate_structural(
    configuration: Mapping[str, object],
    usage: Mapping[str, object],
    catalog: PricingCatalog,
) -> CostEstimate:
    """VPC and Subnet carry no cost of their own in v0.1."""
    return CostEstimate(
        status="priced",
        monthly_cost=to_money(Decimal("0")),
        assumptions=("structural resource: v0.1 assigns no cost to this node itself",),
    )


def calculate_ec2(
    configuration: Mapping[str, object],
    usage: Mapping[str, object],
    catalog: PricingCatalog,
) -> CostEstimate:
    key = (
        f"ec2/{configuration['operating_system']}/{configuration['tenancy']}"
        f"/{configuration['purchase_option']}/{configuration['instance_type']}"
    )
    hours = _q(usage["hours_per_month"])
    count = _q(usage["instance_count"])
    return _compose(
        catalog,
        [("instance hours", key, hours * count)],
        [
            f"{int(count)} x {configuration['instance_type']} at {float(hours):g} h/month",
            f"on-demand {configuration['operating_system']}, {configuration['tenancy']} tenancy",
        ],
    )


def calculate_ebs(
    configuration: Mapping[str, object],
    usage: Mapping[str, object],
    catalog: PricingCatalog,
) -> CostEstimate:
    volume_type = configuration["volume_type"]
    size = _q(configuration["size_gib"])
    count = _q(usage["volume_count"])
    fraction = _q(usage["month_fraction"])
    return _compose(
        catalog,
        [("provisioned storage", f"ebs/{volume_type}/gb-month", size * count * fraction)],
        [
            f"{int(count)} x {int(size)} GiB {volume_type}"
            f"{'' if fraction == 1 else f' for {float(fraction):g} of the month'}",
            "baseline gp3 performance only: provisioned IOPS and throughput are not priced",
        ],
    )


def calculate_rds(
    configuration: Mapping[str, object],
    usage: Mapping[str, object],
    catalog: PricingCatalog,
) -> CostEstimate:
    engine = configuration["engine"]
    instance_class = configuration["instance_class"]
    storage_type = configuration["storage_type"]
    hours = _q(usage["hours_per_month"])
    count = _q(usage["instance_count"])
    storage = _q(configuration["storage_gib"])
    storage_fraction = _q(usage["storage_month_fraction"])
    return _compose(
        catalog,
        [
            (
                "instance hours",
                f"rds/{engine}/single-az/on-demand/{instance_class}",
                hours * count,
            ),
            (
                "storage",
                f"rds/storage/{storage_type}/gb-month",
                storage * count * storage_fraction,
            ),
        ],
        [
            f"{int(count)} x {instance_class} {engine}, Single-AZ, at {float(hours):g} h/month",
            f"{int(storage)} GiB {storage_type} storage per instance",
        ],
    )


def calculate_alb(
    configuration: Mapping[str, object],
    usage: Mapping[str, object],
    catalog: PricingCatalog,
) -> CostEstimate:
    hours = _q(usage["hours_per_month"])
    count = _q(usage["load_balancer_count"])
    lcu_hours = _q(usage["lcu_hours_per_month"])
    return _compose(
        catalog,
        [
            ("load balancer hours", "alb/load-balancer-hour", hours * count),
            ("LCU hours", "alb/lcu-hour", lcu_hours),
        ],
        [
            f"{int(count)} x {configuration['scheme']} ALB at {float(hours):g} h/month",
            f"{float(lcu_hours):g} LCU-hours/month entered by hand, not measured",
        ],
    )


def calculate_nat_gateway(
    configuration: Mapping[str, object],
    usage: Mapping[str, object],
    catalog: PricingCatalog,
) -> CostEstimate:
    hours = _q(usage["hours_per_month"])
    count = _q(usage["gateway_count"])
    processed = _q(usage["processed_gb_per_month"])
    return _compose(
        catalog,
        [
            ("gateway hours", "nat-gateway/gateway-hour", hours * count),
            ("data processing", "nat-gateway/processed-gb", processed),
        ],
        [
            f"{int(count)} x {configuration['connectivity_type']} NAT gateway "
            f"at {float(hours):g} h/month",
            f"{float(processed):g} GB processed/month entered by hand, not measured",
        ],
    )


Calculator = Callable[[Mapping[str, object], Mapping[str, object], PricingCatalog], CostEstimate]

CALCULATORS: dict[str, Calculator] = {
    "vpc": calculate_structural,
    "subnet": calculate_structural,
    "ec2": calculate_ec2,
    "ebs": calculate_ebs,
    "rds": calculate_rds,
    "alb": calculate_alb,
    "nat-gateway": calculate_nat_gateway,
}
