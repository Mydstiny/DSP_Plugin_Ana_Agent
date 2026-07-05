"""Production balance analysis — identify bottlenecks and surplus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import SnapshotData


@dataclass
class Bottleneck:
    """A production bottleneck: an item with insufficient or excess production."""

    item_id: int
    item_name: str
    net_rate: float  # items/min, negative = deficit
    produced_rate: float
    consumed_rate: float
    severity: str  # "critical" | "moderate" | "surplus"
    root_cause: str | None = None
    suggestion: str | None = None


@dataclass
class RootCause:
    """Root cause analysis for a production deficit."""

    item_id: int
    item_name: str
    cause_type: str  # "raw_shortage" | "power" | "logistics" | "factory_count" | "unknown"
    description: str
    upstream_items: list[str] = field(default_factory=list)


def calculate_production_balance(snapshot: SnapshotData) -> list[Bottleneck]:
    """Analyze production/consumption rates and identify bottlenecks.

    Returns a list of Bottleneck objects sorted by severity.
    """
    bottlenecks: list[Bottleneck] = []

    for item_id_str, stat in snapshot.production.items():
        item_id = int(item_id_str)
        net = stat.net
        rate_per_min = stat.rate_per_min

        # Classify severity
        if net < 0:
            deficit_ratio = abs(net) / max(stat.consumed, 1)
            if deficit_ratio > 0.3:  # >30% deficit
                severity = "critical"
            else:
                severity = "moderate"
        elif net > 0 and stat.consumed == 0:
            severity = "surplus"
            continue  # pure surplus items are informational, skip for now
        else:
            severity = "surplus"

        bottlenecks.append(Bottleneck(
            item_id=item_id,
            item_name=stat.item_name,
            net_rate=rate_per_min * (net / max(stat.produced, 1)) if stat.produced > 0 else -rate_per_min,
            produced_rate=rate_per_min if stat.produced > 0 else 0,
            consumed_rate=rate_per_min if stat.consumed > 0 else 0,
            severity=severity,
        ))

    # Sort: critical first, then moderate, then surplus
    severity_order = {"critical": 0, "moderate": 1, "surplus": 2}
    bottlenecks.sort(key=lambda b: severity_order.get(b.severity, 3))
    return bottlenecks


def trace_deficit_root_cause(
    item_id: int,
    scan_data: dict[str, Any],
    recipe_data: dict[int, dict[str, Any]],
) -> RootCause:
    """Trace the root cause of a production deficit.

    Args:
        item_id: The item experiencing a deficit.
        scan_data: Galaxy scan result (dict with planets, factories, power).
        recipe_data: Recipe database {recipe_id: {inputs: [...], outputs: [...]}}.

    Returns:
        RootCause with cause_type and description.
    """
    item_name = f"Item_{item_id}"
    cause_type = "unknown"
    description = f"Unable to determine root cause for {item_name}."
    upstream_items: list[str] = []

    # Check if there's a recipe for this item
    recipes = recipe_data.get(item_id, {})
    inputs = recipes.get("inputs", [])

    if not inputs:
        # Raw resource — check if miners are present
        miners = _find_buildings_of_type(scan_data, "miner")
        if not miners:
            cause_type = "raw_shortage"
            description = (
                f"{item_name} is a raw resource with no active miners. "
                "Place miners on resource veins."
            )
        else:
            cause_type = "factory_count"
            description = (
                f"{item_name} production insufficient — increase miner count."
            )
        return RootCause(
            item_id=item_id,
            item_name=item_name,
            cause_type=cause_type,
            description=description,
        )

    # Manufactured item — check upstream
    for inp in inputs:
        upstream_id = inp.get("item_id", 0)
        upstream_name = inp.get("item_name", f"Item_{upstream_id}")
        rate = inp.get("rate_per_min", 0)

        # Check if upstream is in deficit
        upstream_stat = _find_item_stat(scan_data, upstream_id)
        if upstream_stat:
            net = upstream_stat.get("net", 0)
            if net < 0:
                upstream_items.append(upstream_name)
                cause_type = "raw_shortage"

    if cause_type == "raw_shortage":
        description = (
            f"{item_name} deficit caused by upstream shortage: "
            f"{', '.join(upstream_items)}. Increase production of these items."
        )
    elif cause_type == "unknown":
        # Check power
        power_ok = _check_power_for_item(scan_data, item_id)
        if not power_ok:
            cause_type = "power"
            description = (
                f"{item_name} production affected by power shortage. "
                "Add power generation to the planet."
            )
        else:
            cause_type = "factory_count"
            description = (
                f"{item_name} production rate is below demand. "
                f"Add more factories producing {item_name}."
            )

    return RootCause(
        item_id=item_id,
        item_name=item_name,
        cause_type=cause_type,
        description=description,
        upstream_items=upstream_items,
    )


def _find_buildings_of_type(
    scan_data: dict[str, Any], building_type: str
) -> list[dict]:
    """Find all buildings of a given type in the scan data."""
    result: list[dict] = []
    for planet in scan_data.get("planets", []):
        for factory in planet.get("factories", []):
            if factory.get("type") == building_type:
                result.append(factory)
    return result


def _find_item_stat(
    scan_data: dict[str, Any], item_id: int
) -> dict[str, Any] | None:
    """Find production stat for an item from scan data."""
    production = scan_data.get("production", {})
    return production.get(str(item_id))


def _check_power_for_item(
    scan_data: dict[str, Any], item_id: int
) -> bool:
    """Check if power is sufficient for a given item's planet."""
    # Simplified — in real implementation, check the planet where this item
    # is produced. For now, assume power is OK.
    return True
