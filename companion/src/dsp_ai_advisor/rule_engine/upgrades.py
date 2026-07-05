"""Upgrade scanning — identify available tech and building improvements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class UpgradeOpportunity:
    """An available upgrade for a building, belt, or sorter."""

    building_type: str  # "belt" | "sorter" | "assembler" | "smelter" | "miner"
    current_level: int
    max_level: int
    planet_name: str
    count: int  # how many instances can be upgraded
    benefit: str  # human-readable benefit description
    priority: str  # "high" | "medium" | "low"


# Known upgrade paths in DSP
_UPGRADE_TIERS = {
    "belt": {
        "name": "传送带",
        "levels": {
            1: {"speed": 6, "name": "Conveyor Belt MK.I"},
            2: {"speed": 12, "name": "Conveyor Belt MK.II"},
            3: {"speed": 30, "name": "Conveyor Belt MK.III"},
        },
    },
    "sorter": {
        "name": "分拣器",
        "levels": {
            1: {"speed": 1.5, "name": "Sorter MK.I"},
            2: {"speed": 3.0, "name": "Sorter MK.II"},
            3: {"speed": 6.0, "name": "Sorter MK.III"},
        },
    },
    "assembler": {
        "name": "制造台",
        "levels": {
            1: {"speed": 0.75, "name": "Assembling Machine MK.I"},
            2: {"speed": 1.0, "name": "Assembling Machine MK.II"},
            3: {"speed": 1.5, "name": "Assembling Machine MK.III"},
        },
    },
    "smelter": {
        "name": "冶炼炉",
        "levels": {
            1: {"speed": 1.0, "name": "Smelter MK.I"},
            2: {"speed": 2.0, "name": "Smelter MK.II"},
        },
    },
}


def scan_available_upgrades(scan_data: dict[str, Any]) -> list[UpgradeOpportunity]:
    """Scan all planets for available building upgrades.

    Compares current building levels against unlocked tech levels
    and returns upgrade opportunities sorted by priority.
    """
    opportunities: list[UpgradeOpportunity] = []
    unlocked_tech = set(scan_data.get("unlocked_tech", []))

    # Determine max available level for each building type
    max_levels = _get_max_available_levels(unlocked_tech)

    for planet in scan_data.get("planets", []):
        planet_name = planet.get("planet_name", "Unknown")

        # Check belts
        for level in range(1, max_levels.get("belt", 1)):
            count = _count_buildings_at_level(planet, "belt", level)
            if count > 0:
                target = min(level + 1, max_levels.get("belt", level + 1))
                if target > level:
                    opportunities.append(UpgradeOpportunity(
                        building_type="belt",
                        current_level=level,
                        max_level=target,
                        planet_name=planet_name,
                        count=count,
                        benefit=_belt_benefit(level, target, count),
                        priority="medium",
                    ))

        # Check sorters
        for level in range(1, max_levels.get("sorter", 1)):
            count = _count_buildings_at_level(planet, "sorter", level)
            if count > 0:
                target = min(level + 1, max_levels.get("sorter", level + 1))
                if target > level:
                    opportunities.append(UpgradeOpportunity(
                        building_type="sorter",
                        current_level=level,
                        max_level=target,
                        planet_name=planet_name,
                        count=count,
                        benefit=_sorter_benefit(level, target, count),
                        priority="medium",
                    ))

        # Check assemblers
        for level in range(1, max_levels.get("assembler", 1)):
            count = _count_buildings_at_level(planet, "assembler", level)
            if count > 0:
                target = min(level + 1, max_levels.get("assembler", level + 1))
                if target > level:
                    opportunities.append(UpgradeOpportunity(
                        building_type="assembler",
                        current_level=level,
                        max_level=target,
                        planet_name=planet_name,
                        count=count,
                        benefit=(
                            f"Upgrade {count} assemblers to MK.{target} "
                            f"(speed +{_speed_increase('assembler', level, target):.0%})"
                        ),
                        priority="high",
                    ))

        # Check smelters
        for level in range(1, max_levels.get("smelter", 1)):
            count = _count_buildings_at_level(planet, "smelter", level)
            if count > 0:
                target = min(level + 1, max_levels.get("smelter", level + 1))
                if target > level:
                    opportunities.append(UpgradeOpportunity(
                        building_type="smelter",
                        current_level=level,
                        max_level=target,
                        planet_name=planet_name,
                        count=count,
                        benefit=(
                            f"Upgrade {count} smelters to MK.{target} "
                            f"(speed +{_speed_increase('smelter', level, target):.0%})"
                        ),
                        priority="high",
                    ))

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    opportunities.sort(key=lambda o: priority_order.get(o.priority, 3))
    return opportunities


def _get_max_available_levels(unlocked_tech: set[str]) -> dict[str, int]:
    """Determine max building level based on unlocked tech."""
    max_levels: dict[str, int] = {}
    for btype, info in _UPGRADE_TIERS.items():
        max_levels[btype] = 1
        for level in sorted(info["levels"].keys(), reverse=True):
            tier_name = info["levels"][level]["name"]
            # Check if this tier is unlocked (fuzzy match)
            if any(tier_name.lower() in t.lower() for t in unlocked_tech):
                max_levels[btype] = level
                break
    return max_levels


def _count_buildings_at_level(
    planet: dict[str, Any], building_type: str, level: int
) -> int:
    """Count buildings of a specific type and level on a planet."""
    count = 0
    for factory in planet.get("factories", []):
        if factory.get("type") == building_type:
            if factory.get("level") == level or (
                "MK." in str(factory.get("level_name", ""))
                and str(factory.get("level_name")).endswith(f"MK.{level}")
            ):
                count += 1
    return count


def _speed_increase(building_type: str, from_level: int, to_level: int) -> float:
    """Calculate speed improvement percentage."""
    tiers = _UPGRADE_TIERS.get(building_type, {}).get("levels", {})
    from_speed = tiers.get(from_level, {}).get("speed", 1.0)
    to_speed = tiers.get(to_level, {}).get("speed", 1.0)
    if from_speed == 0:
        return 0.0
    return (to_speed - from_speed) / from_speed


def _belt_benefit(from_level: int, to_level: int, count: int) -> str:
    tiers = _UPGRADE_TIERS["belt"]["levels"]
    from_speed = tiers.get(from_level, {}).get("speed", 6)
    to_speed = tiers.get(to_level, {}).get("speed", 30)
    return (
        f"Upgrade {count} belts from MK.{from_level} to MK.{to_level} "
        f"(speed {from_speed}→{to_speed}/s)"
    )


def _sorter_benefit(from_level: int, to_level: int, count: int) -> str:
    return (
        f"Upgrade {count} sorters from MK.{from_level} to MK.{to_level} "
        f"(speed +{_speed_increase('sorter', from_level, to_level):.0%})"
    )
