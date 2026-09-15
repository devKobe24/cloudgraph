"""Pricing catalog and per-resource calculators.

Rules that do not bend (guide sections 13.1 / 13.9):
- no network calls, ever; the catalog is a local versioned file
- money is Decimal, never float
- a missing rate returns status "unpriced", never a silent 0
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
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
    key = "/".join(
        (
            "ec2",
            str(configuration["operating_system"]),
            str(configuration["tenancy"]),
            str(configuration["purchase_option"]),
            str(configuration["instance_type"]),
        )
    )
    rate = catalog.lookup(key)
    if rate is None:
        return unpriced(key)

    hours = Decimal(str(usage["hours_per_month"]))
    count = Decimal(str(usage["instance_count"]))
    compute = to_money(rate * hours * count)
    return CostEstimate(
        status="priced",
        monthly_cost=compute,
        breakdown=(CostItem("instance hours", compute, "USD"),),
        assumptions=(
            f"{int(count)} x {configuration['instance_type']} at {float(hours):g} h/month",
            f"on-demand {configuration['operating_system']}, {configuration['tenancy']} tenancy",
        ),
    )


Calculator = Callable[[Mapping[str, object], Mapping[str, object], PricingCatalog], CostEstimate]

CALCULATORS: dict[str, Calculator] = {
    "vpc": calculate_structural,
    "subnet": calculate_structural,
    "ec2": calculate_ec2,
}
