"""Power grid analysis — identify surplus and deficit planets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PowerIssue:
    """A power-related issue on a specific planet."""

    planet_id: int
    planet_name: str
    generation: float  # MW
    consumption: float  # MW
    surplus: float  # MW (negative = deficit)
    satisfaction: float  # 0.0 - 1.0
    severity: str  # "critical" | "warning" | "ok"


def analyze_power(scan_data: dict[str, Any]) -> list[PowerIssue]:
    """Analyze power grid across all planets.

    Returns a list of PowerIssue sorted by severity (critical planets first).
    """
    issues: list[PowerIssue] = []

    for planet in _get_power_data(scan_data):
        generation = planet.get("power_generation", 0.0)
        consumption = planet.get("power_consumption", 0.0)
        surplus = generation - consumption
        satisfaction = (
            min(generation / max(consumption, 0.001), 1.0)
            if consumption > 0
            else 1.0
        )

        if satisfaction < 0.2:
            severity = "critical"
        elif satisfaction < 0.5:
            severity = "warning"
        else:
            severity = "ok"

        issues.append(PowerIssue(
            planet_id=planet.get("planet_id", 0),
            planet_name=planet.get("planet_name", "Unknown"),
            generation=generation,
            consumption=consumption,
            surplus=round(surplus, 1),
            satisfaction=round(satisfaction, 2),
            severity=severity,
        ))

    # Critical first, then warning, then ok
    severity_order = {"critical": 0, "warning": 1, "ok": 2}
    issues.sort(key=lambda i: severity_order.get(i.severity, 3))
    return issues


def calculate_power_recommendation(issue: PowerIssue) -> str:
    """Generate a concrete recommendation for a power issue."""
    deficit = abs(issue.surplus)

    if issue.severity == "critical" and issue.surplus < 0:
        # Rough estimate: fusion plant = 15 MW, solar panel = 0.36 MW
        fusion_needed = max(1, int(deficit / 15) + 1)
        solar_needed = max(1, int(deficit / 0.36) + 1)
        return (
            f"{issue.planet_name}: {deficit:.0f}MW deficit. "
            f"Add ~{fusion_needed} fusion plants or ~{solar_needed} solar panels."
        )
    elif issue.severity == "warning" and issue.surplus < 0:
        return (
            f"{issue.planet_name}: {deficit:.0f}MW shortage. "
            "Consider adding power generation."
        )
    elif issue.surplus > 0:
        return (
            f"{issue.planet_name}: {issue.surplus:.0f}MW surplus. "
            "Power is sufficient."
        )
    else:
        return f"{issue.planet_name}: Power balanced."


def _get_power_data(scan_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract power data from scan result."""
    planets = scan_data.get("planets", [])
    if not planets:
        # Fallback: use top-level power_stats if available
        power_stats = scan_data.get("power_stats", {})
        if power_stats:
            return [
                {
                    "planet_id": pid,
                    "planet_name": pdata.get("planet_name", f"Planet_{pid}"),
                    "power_generation": pdata.get("generation", 0.0),
                    "power_consumption": pdata.get("consumption", 0.0),
                }
                for pid, pdata in power_stats.items()
            ]
    return planets
