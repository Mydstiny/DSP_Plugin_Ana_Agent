"""Logistics analysis — route efficiency, station grouping suggestions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogisticsIssue:
    """A logistics route or station efficiency issue."""

    station_id: int
    station_name: str
    planet_name: str
    issue_type: str  # "route_underutilized" | "station_full" | "route_bottleneck"
    description: str
    current_utilization: float = 0.0  # 0.0 - 1.0


@dataclass
class GroupingSuggestion:
    """Suggestion for station naming and grouping."""

    planet_name: str
    current_name: str
    suggested_name: str
    reason: str


def analyze_routes(scan_data: dict[str, Any]) -> list[LogisticsIssue]:
    """Analyze interstellar logistics routes for inefficiencies.

    Returns issues sorted by severity (underutilized routes first).
    """
    issues: list[LogisticsIssue] = []
    routes = scan_data.get("routes", [])

    for route in routes:
        utilization = route.get("utilization", 1.0)
        station_id = route.get("station_id", 0)
        station_name = route.get("station_name", f"Station_{station_id}")
        planet_name = route.get("planet_name", "Unknown")
        item_name = route.get("item_name", "Unknown")

        if utilization < 0.3:
            issues.append(LogisticsIssue(
                station_id=station_id,
                station_name=station_name,
                planet_name=planet_name,
                issue_type="route_underutilized",
                description=(
                    f"Route {item_name}: {station_name} on {planet_name} "
                    f"utilization only {utilization:.0%}. Consider reducing "
                    "transport vessels or reallocating."
                ),
                current_utilization=utilization,
            ))
        elif utilization > 0.9:
            issues.append(LogisticsIssue(
                station_id=station_id,
                station_name=station_name,
                planet_name=planet_name,
                issue_type="route_bottleneck",
                description=(
                    f"Route {item_name}: {station_name} on {planet_name} "
                    f"at {utilization:.0%} capacity. Consider adding vessels "
                    "or upgrading station."
                ),
                current_utilization=utilization,
            ))

    # Check stations for fullness
    for station in scan_data.get("stations", []):
        for slot in station.get("slots", []):
            if slot.get("fill_ratio", 0.0) > 0.95:
                issues.append(LogisticsIssue(
                    station_id=station.get("station_id", 0),
                    station_name=station.get("station_name", "Unknown"),
                    planet_name=station.get("planet_name", "Unknown"),
                    issue_type="station_full",
                    description=(
                        f"Station {station.get('station_name')} slot "
                        f"{slot.get('item_name')} is {slot['fill_ratio']:.0%} full. "
                        "Output is blocked."
                    ),
                    current_utilization=slot["fill_ratio"],
                ))

    return issues


def suggest_grouping(
    planet_name: str, scan_data: dict[str, Any]
) -> list[GroupingSuggestion]:
    """Analyze station naming and suggest consistent grouping.

    Recommended format: [星球]-[产物]-[序号]
    Example: "铸星-钛晶石-01", "母星-铁块-02"
    """
    suggestions: list[GroupingSuggestion] = []
    stations = scan_data.get("stations", [])

    for station in stations:
        if station.get("planet_name") != planet_name:
            continue

        current_name = station.get("station_name", "")
        if not current_name:
            continue

        # Detect non-standard names
        if _name_is_standard(current_name, planet_name):
            continue

        # Infer product from station contents
        primary_item = _infer_primary_item(station)
        if not primary_item:
            continue

        # Find next available index for this pattern
        existing_indices = _get_existing_indices(stations, planet_name, primary_item)
        next_index = max(existing_indices) + 1 if existing_indices else 1

        suggested_name = f"{planet_name}-{primary_item}-{next_index:02d}"

        suggestions.append(GroupingSuggestion(
            planet_name=planet_name,
            current_name=current_name,
            suggested_name=suggested_name,
            reason=f"Standardize naming to '{planet_name}-{primary_item}-NN' format",
        ))

    return suggestions


def _name_is_standard(name: str, planet: str) -> bool:
    """Check if a station name follows the standard pattern."""
    expected_prefix = f"{planet}-"
    return name.startswith(expected_prefix) and len(name.split("-")) == 3


def _infer_primary_item(station: dict[str, Any]) -> str:
    """Infer the primary item a station handles."""
    slots = station.get("slots", [])
    if not slots:
        return ""

    # The slot with the most inventory is the primary
    max_fill = 0
    primary = ""
    for slot in slots:
        fill = slot.get("fill_ratio", 0.0)
        if fill > max_fill:
            max_fill = fill
            primary = slot.get("item_name", "")
    return primary


def _get_existing_indices(
    stations: list[dict[str, Any]], planet: str, item: str
) -> list[int]:
    """Find existing station indices for the same planet+item pattern."""
    prefix = f"{planet}-{item}-"
    indices: list[int] = []
    for s in stations:
        name = s.get("station_name", "")
        if name.startswith(prefix):
            try:
                indices.append(int(name.rsplit("-", 1)[-1]))
            except (ValueError, IndexError):
                continue
    return indices
