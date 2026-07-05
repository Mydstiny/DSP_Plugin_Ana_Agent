using System;
using System.Collections.Generic;
using DSP_AI_Advisor.WebSocket;

namespace DSP_AI_Advisor.AlertEngine
{
    /// <summary>
    /// Layer 1 real-time alert engine — checks critical conditions every tick.
    /// Alerts are pushed via WebSocket /alert channel to the Companion.
    ///
    /// All checks are O(1) and must never throw — this runs on the game thread.
    /// </summary>
    public static class AlertEngine
    {
        // ── Thresholds ─────────────────────────────────────────

        private const double POWER_CRITICAL_THRESHOLD = 0.20;  // <20% satisfaction
        private const double STATION_FULL_THRESHOLD = 0.95;     // >95% full
        private const int STALL_TIMEOUT_SECONDS = 60;           // stalled >60s

        // ── State (prevents duplicate alerts) ──────────────────

        private static readonly HashSet<string> _activeAlerts = new();
        private static readonly Dictionary<string, double> _lastAlertTime = new();
        private const double ALERT_COOLDOWN_SECONDS = 30.0;  // don't repeat same alert <30s

        // ── Public API ─────────────────────────────────────────

        /// <summary>
        /// Check power status for a planet. Call from ProductionCollector or
        /// a Harmony patch on PowerSystem.
        /// </summary>
        public static void CheckPower(int planetId, string planetName,
            double generation, double consumption)
        {
            double satisfaction = consumption > 0
                ? generation / consumption
                : 1.0;

            var alertId = $"power_{planetId}";

            if (satisfaction < POWER_CRITICAL_THRESHOLD)
            {
                if (ShouldSend(alertId))
                {
                    SendAlert("power_critical", new
                    {
                        planet_id = planetId,
                        planet_name = planetName,
                        ratio = Math.Round(satisfaction, 2),
                        generation = Math.Round(generation, 1),
                        consumption = Math.Round(consumption, 1),
                    });

                    Plugin.Log.LogWarning(
                        $"[AlertEngine] POWER CRITICAL: {planetName} " +
                        $"satisfaction={satisfaction:P0} ({generation:F0}MW/{consumption:F0}MW)");
                }
            }
            else
            {
                ClearAlert(alertId);
            }
        }

        /// <summary>
        /// Check if a station slot is full/blocked.
        /// </summary>
        public static void CheckStationFull(int stationId, string stationName,
            string planetName, int itemId, string itemName, double fillRatio)
        {
            var alertId = $"station_full_{stationId}_{itemId}";

            if (fillRatio > STATION_FULL_THRESHOLD)
            {
                if (ShouldSend(alertId))
                {
                    SendAlert("station_full", new
                    {
                        station_id = stationId,
                        station_name = stationName,
                        planet_name = planetName,
                        item_id = itemId,
                        item_name = itemName,
                        capacity_ratio = Math.Round(fillRatio, 2),
                    });

                    Plugin.Log.LogWarning(
                        $"[AlertEngine] STATION FULL: {stationName} " +
                        $"{itemName} at {fillRatio:P0}");
                }
            }
            else
            {
                ClearAlert(alertId);
            }
        }

        /// <summary>
        /// Check if production has stalled on a planet.
        /// </summary>
        public static void CheckProductionStalled(int planetId, string planetName,
            int factoryId, string reason, double stalledSeconds)
        {
            if (stalledSeconds < STALL_TIMEOUT_SECONDS) return;

            var alertId = $"stalled_{planetId}_{factoryId}";

            if (ShouldSend(alertId))
            {
                SendAlert("production_stalled", new
                {
                    planet_id = planetId,
                    planet_name = planetName,
                    factory_id = factoryId,
                    reason,
                });

                Plugin.Log.LogWarning(
                    $"[AlertEngine] STALLED: {planetName} factory#{factoryId} " +
                    $"({reason}, {stalledSeconds:F0}s)");
            }
        }

        /// <summary>
        /// Check if a resource vein is depleted.
        /// </summary>
        public static void CheckResourceDepleted(int planetId, string planetName,
            int veinId, int itemId, string itemName)
        {
            var alertId = $"resource_{planetId}_{veinId}";

            if (ShouldSend(alertId))
            {
                SendAlert("resource_depleted", new
                {
                    planet_id = planetId,
                    planet_name = planetName,
                    vein_id = veinId,
                    item_id = itemId,
                    item_name = itemName,
                });

                Plugin.Log.LogWarning(
                    $"[AlertEngine] RESOURCE DEPLETED: {planetName} " +
                    $"{itemName} vein#{veinId}");
            }
        }

        // ── Internal ───────────────────────────────────────────

        private static bool ShouldSend(string alertId)
        {
            if (_activeAlerts.Contains(alertId)) return false;

            if (_lastAlertTime.TryGetValue(alertId, out var lastTime))
            {
                var elapsed = (DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds - lastTime;
                if (elapsed < ALERT_COOLDOWN_SECONDS) return false;
            }

            _activeAlerts.Add(alertId);
            _lastAlertTime[alertId] =
                (DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds;
            return true;
        }

        private static void ClearAlert(string alertId)
        {
            _activeAlerts.Remove(alertId);
        }

        private static void SendAlert(string type, object payload)
        {
            try
            {
                var json = MessageCodec.Encode("alert", type, payload);
                WsServer.Instance.Broadcast(json);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[AlertEngine] Failed to send alert: {ex.Message}");
            }
        }
    }
}
