"""Tests for rule engine — production balance, power, logistics, upgrades."""

import pytest
from dsp_ai_advisor.models import SnapshotData, ItemStat, SnapshotSummary
from dsp_ai_advisor.rule_engine.production import calculate_production_balance
from dsp_ai_advisor.rule_engine.power import analyze_power
from dsp_ai_advisor.rule_engine.logistics import analyze_routes
from dsp_ai_advisor.rule_engine.upgrades import scan_available_upgrades


# ── Production Balance ───────────────────────────────────────

class TestProductionBalance:
    def test_deficit_detection(self):
        """Items with net negative should be flagged as deficits."""
        snap = SnapshotData(
            snapshot_id="test1",
            game_tick=6000,
            elapsed_seconds=5.0,
            timestamp_unix=1000,
            production={
                "1001": ItemStat(
                    item_id=1001, item_name="铜板",
                    produced=500, consumed=1000, net=-500, rate_per_min=100.0,
                ),
            },
            summary=SnapshotSummary(total_items_tracked=1, items_in_deficit=1, items_in_surplus=0),
        )

        results = calculate_production_balance(snap)
        assert len(results) == 1
        assert results[0].item_name == "铜板"
        assert results[0].severity == "critical"  # 50% deficit
        assert results[0].net_rate < 0

    def test_surplus_skipped_when_no_consumer(self):
        """Pure surplus items (consumed=0) should not appear."""
        snap = SnapshotData(
            snapshot_id="test2",
            game_tick=6000,
            elapsed_seconds=5.0,
            timestamp_unix=1000,
            production={
                "2001": ItemStat(
                    item_id=2001, item_name="石矿",
                    produced=5000, consumed=0, net=5000, rate_per_min=1000.0,
                ),
            },
            summary=SnapshotSummary(total_items_tracked=1, items_in_deficit=0, items_in_surplus=1),
        )

        results = calculate_production_balance(snap)
        assert len(results) == 0

    def test_empty_snapshot(self):
        """Empty snapshot should return empty list."""
        snap = SnapshotData(
            snapshot_id="empty",
            game_tick=0,
            elapsed_seconds=0.0,
            timestamp_unix=0,
        )
        results = calculate_production_balance(snap)
        assert results == []


# ── Power Analysis ──────────────────────────────────────────

class TestPowerAnalysis:
    def test_critical_power_planet(self):
        """Planet with <20% power satisfaction should be critical."""
        scan = {
            "planets": [
                {
                    "planet_id": 1,
                    "planet_name": "母星",
                    "power_generation": 50.0,
                    "power_consumption": 300.0,
                },
            ],
        }

        issues = analyze_power(scan)
        assert len(issues) == 1
        assert issues[0].planet_name == "母星"
        assert issues[0].severity == "critical"
        assert issues[0].surplus < 0

    def test_healthy_planet(self):
        """Planet with surplus power should be ok."""
        scan = {
            "planets": [
                {
                    "planet_id": 2,
                    "planet_name": "铸星",
                    "power_generation": 500.0,
                    "power_consumption": 200.0,
                },
            ],
        }

        issues = analyze_power(scan)
        assert issues[0].severity == "ok"
        assert issues[0].surplus > 0


# ── Logistics Analysis ──────────────────────────────────────

class TestLogisticsAnalysis:
    def test_underutilized_route(self):
        """Route with low utilization should be flagged."""
        scan = {
            "routes": [
                {
                    "station_id": 1,
                    "station_name": "ILS-A",
                    "planet_name": "母星",
                    "utilization": 0.15,
                    "item_name": "铁矿",
                },
            ],
            "stations": [],
        }

        issues = analyze_routes(scan)
        assert len(issues) >= 1
        assert any(i.issue_type == "route_underutilized" for i in issues)

    def test_station_full(self):
        """Station with 95%+ fill ratio should be flagged."""
        scan = {
            "routes": [],
            "stations": [
                {
                    "station_id": 10,
                    "station_name": "ILS-B",
                    "planet_name": "母星",
                    "slots": [
                        {
                            "item_name": "铁块",
                            "fill_ratio": 0.98,
                        },
                    ],
                },
            ],
        }

        issues = analyze_routes(scan)
        assert any(i.issue_type == "station_full" for i in issues)


# ── Upgrade Scanning ────────────────────────────────────────

class TestUpgradeScanning:
    def test_no_upgrades_when_already_max(self):
        """When all buildings are at max level, no upgrades needed."""
        scan = {
            "unlocked_tech": [
                "Assembling Machine MK.III",
                "Smelter MK.II",
                "Conveyor Belt MK.III",
            ],
            "planets": [
                {
                    "planet_name": "母星",
                    "factories": [
                        {"type": "assembler", "level": 3, "level_name": "MK.III"},
                        {"type": "belt", "level": 3},
                    ],
                },
            ],
        }

        results = scan_available_upgrades(scan)
        assert len(results) == 0

    def test_known_upgrade_detected(self):
        """Known upgrade tiers are detected."""
        scan = {
            "unlocked_tech": [
                "Assembling Machine MK.II",
                "Assembling Machine MK.III",
            ],
            "planets": [
                {
                    "planet_name": "母星",
                    "factories": [
                        {"type": "assembler", "level": 1, "level_name": "MK.I"},
                        {"type": "assembler", "level": 1, "level_name": "MK.I"},
                        {"type": "assembler", "level": 1, "level_name": "MK.I"},
                    ],
                },
            ],
        }

        results = scan_available_upgrades(scan)
        # Should find MK.I → MK.II and MK.I → MK.III opportunities
        assert len(results) > 0
