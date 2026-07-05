using System;
using System.Collections.Generic;
using HarmonyLib;

namespace DSP_AI_Advisor.DataCollectors
{
    /// <summary>
    /// 全星系深度扫描 — 遍历所有星球、工厂、物流塔、航线，生成完整快照.
    ///
    /// 触发方式: WebSocket /command channel 收到 "trigger_scan" 消息时调用.
    /// 扫描结果通过 WsServer.BroadcastGalaxyScan() 推送，类型为 galaxy_scan_result.
    /// </summary>
    public static class GalaxyScanner
    {
        /// <summary>
        /// 执行全星系扫描，返回结构化数据字典.
        /// 调用时机: Player 点击"全星系分析"按钮，或 Companion 发送 trigger_scan.
        ///
        /// 注意: 此方法访问大量游戏对象，应在新线程上异步执行 (await Task.Run).
        /// 不要在 Unity 主线程上同步调用，可能导致卡顿 1-3 秒.
        /// </summary>
        public static GalaxyScanData Scan()
        {
            var data = new GalaxyScanData
            {
                ScanId = Guid.NewGuid().ToString("N")[..8],
                TimestampUnix = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            };

            try
            {
                // 遍历所有星球
                var gameData = GameMain.data;
                if (gameData == null)
                {
                    data.Error = "GameMain.data is null — game not loaded?";
                    return data;
                }

                var planets = new List<PlanetScanEntry>();

                for (int i = 0; i < gameData.planetCount; i++)
                {
                    var planetData = gameData.planets[i];
                    if (planetData == null) continue;

                    var planetEntry = ScanPlanet(planetData);
                    planets.Add(planetEntry);
                }

                data.Planets = planets.ToArray();

                // 采集科技状态
                data.UnlockedTech = CollectTechState(gameData);

                // 采集星际航线
                data.Routes = CollectRoutes(gameData);

                // 采集物流塔
                data.Stations = CollectStations(gameData);

                Plugin.Log.LogInfo(
                    $"[GalaxyScanner] Scan complete: {planets.Count} planets, " +
                    $"{data.Stations.Length} stations, {data.Routes.Length} routes"
                );
            }
            catch (Exception ex)
            {
                data.Error = $"Scan failed: {ex.Message}";
                Plugin.Log.LogError($"[GalaxyScanner] {data.Error}");
            }

            return data;
        }

        /// <summary>
        /// 扫描单个星球.
        /// </summary>
        private static PlanetScanEntry ScanPlanet(PlanetData planetData)
        {
            var entry = new PlanetScanEntry
            {
                PlanetId = planetData.id,
                PlanetName = planetData.displayName ?? $"Planet_{planetData.id}",
                StarName = planetData.star?.displayName ?? "Unknown",
            };

            var factory = planetData.factory;
            if (factory == null)
            {
                entry.IsFactoryBuilt = false;
                return entry;
            }

            entry.IsFactoryBuilt = true;
            var factories = new List<FactoryEntry>();

            // 扫描工厂建筑 (assemblers, smelters, chemical plants, etc.)
            for (int i = 1; i < factory.entityCursor; i++)
            {
                var entity = factory.entityPool[i];
                if (entity == null || entity.id != i) continue;

                var fEntry = new FactoryEntry
                {
                    Id = i,
                    Type = GetBuildingType(entity),
                    Level = entity.level,
                    RecipeId = entity.recipeId,
                };

                // 判断工作状态
                if (entity.recipeId == 0)
                {
                    fEntry.Status = "idle";
                    fEntry.Reason = "no_recipe";
                }
                else if (entity.powerConns == null || entity.powerConns.Length == 0)
                {
                    fEntry.Status = "idle";
                    fEntry.Reason = "no_power";
                }
                else
                {
                    // 简化为 active — 详细状态需更多内部 API
                    fEntry.Status = "active";
                }

                factories.Add(fEntry);
            }

            entry.Factories = factories.ToArray();
            entry.TotalFactories = factories.Count;

            // 电力数据
            var powerSystem = factory.powerSystem;
            if (powerSystem != null)
            {
                entry.PowerGeneration = powerSystem.genEnergyPerTick * 60.0 / 1000000.0;
                entry.PowerConsumption = powerSystem.consumeEnergyPerTick * 60.0 / 1000000.0;
            }

            return entry;
        }

        /// <summary>
        /// 采集已解锁科技列表.
        /// </summary>
        private static string[] CollectTechState(GameData gameData)
        {
            var techList = new List<string>();
            var history = gameData.history;

            if (history?.techStates != null)
            {
                foreach (var tech in history.techStates)
                {
                    if (tech.unlocked)
                    {
                        // tech 名称需要从 ProtoSet 查找
                        techList.Add($"Tech_{tech.techId}");
                    }
                }
            }

            return techList.ToArray();
        }

        /// <summary>
        /// 采集星际物流航线.
        /// </summary>
        private static RouteEntry[] CollectRoutes(GameData gameData)
        {
            var routes = new List<RouteEntry>();

            // 航线数据存储在各个物流塔中
            // 通过遍历所有星球的物流塔来采集
            for (int i = 0; i < gameData.planetCount; i++)
            {
                var planetData = gameData.planets[i];
                if (planetData?.factory?.transport == null) continue;

                var transport = planetData.factory.transport;
                for (int j = 0; j < transport.stationCursor; j++)
                {
                    var station = transport.stationPool[j];
                    if (station == null || station.id != j) continue;

                    // 每个物流塔的每条航线
                    for (int k = 0; k < station.slots.Length; k++)
                    {
                        var slot = station.slots[k];
                        if (slot == null || slot.storage == null) continue;

                        // 检查是否有远程供需
                        if (slot.remoteSupplyLogic == 0 && slot.remoteDemandLogic == 0)
                            continue;

                        routes.Add(new RouteEntry
                        {
                            StationId = station.id,
                            StationName = station.name ?? $"ILS-{station.id}",
                            PlanetName = planetData.displayName ?? $"Planet_{planetData.id}",
                            ItemName = $"Item_{slot.itemId}",
                            ItemId = slot.itemId,
                            SupplyLogic = slot.remoteSupplyLogic,
                            DemandLogic = slot.remoteDemandLogic,
                        });
                    }
                }
            }

            return routes.ToArray();
        }

        /// <summary>
        /// 采集物流塔信息.
        /// </summary>
        private static StationEntry[] CollectStations(GameData gameData)
        {
            var stations = new List<StationEntry>();

            for (int i = 0; i < gameData.planetCount; i++)
            {
                var planetData = gameData.planets[i];
                if (planetData?.factory?.transport == null) continue;

                var transport = planetData.factory.transport;
                for (int j = 0; j < transport.stationCursor; j++)
                {
                    var station = transport.stationPool[j];
                    if (station == null || station.id != j) continue;

                    var slots = new List<StationSlotEntry>();
                    for (int k = 0; k < station.slots.Length; k++)
                    {
                        var slot = station.slots[k];
                        if (slot?.storage == null) continue;

                        int count = 0;
                        int maxCount = slot.storage.maxItemCount;

                        // 计算存储量
                        for (int itemIdx = 0; itemIdx < slot.storage.itemId.Length; itemIdx++)
                        {
                            count += slot.storage.count[itemIdx];
                        }

                        double fillRatio = maxCount > 0 ? (double)count / maxCount : 0;

                        slots.Add(new StationSlotEntry
                        {
                            ItemId = slot.itemId,
                            ItemName = $"Item_{slot.itemId}",
                            Count = count,
                            MaxCount = maxCount,
                            FillRatio = Math.Round(fillRatio, 2),
                        });
                    }

                    stations.Add(new StationEntry
                    {
                        StationId = station.id,
                        StationName = station.name ?? $"ILS-{station.id}",
                        PlanetName = planetData.displayName ?? $"Planet_{planetData.id}",
                        Slots = slots.ToArray(),
                        IsInterstellar = station.isStellar,
                        VesselCount = station.vesselCount,
                        DockCount = station.dockCount,
                    });
                }
            }

            return stations.ToArray();
        }

        /// <summary>
        /// 判断建筑类型字符串.
        /// </summary>
        private static string GetBuildingType(EntityData entity)
        {
            // 简化判断 — 实际 DSP 中可以通过 entity.protoId 查 ProtoSet
            if (entity.assemblerId > 0 && entity.labId == 0) return "assembler";
            if (entity.labId > 0) return "lab";
            return "factory";
        }
    }

    // ── 数据模型 ──────────────────────────────────────────────

    [Serializable]
    public class GalaxyScanData
    {
        [Newtonsoft.Json.JsonProperty("scan_id")]
        public string ScanId { get; set; }

        [Newtonsoft.Json.JsonProperty("timestamp_unix")]
        public long TimestampUnix { get; set; }

        [Newtonsoft.Json.JsonProperty("planets")]
        public PlanetScanEntry[] Planets { get; set; } = Array.Empty<PlanetScanEntry>();

        [Newtonsoft.Json.JsonProperty("stations")]
        public StationEntry[] Stations { get; set; } = Array.Empty<StationEntry>();

        [Newtonsoft.Json.JsonProperty("routes")]
        public RouteEntry[] Routes { get; set; } = Array.Empty<RouteEntry>();

        [Newtonsoft.Json.JsonProperty("unlocked_tech")]
        public string[] UnlockedTech { get; set; } = Array.Empty<string>();

        [Newtonsoft.Json.JsonProperty("error")]
        public string Error { get; set; }
    }

    [Serializable]
    public class PlanetScanEntry
    {
        [Newtonsoft.Json.JsonProperty("planet_id")]
        public int PlanetId { get; set; }

        [Newtonsoft.Json.JsonProperty("planet_name")]
        public string PlanetName { get; set; }

        [Newtonsoft.Json.JsonProperty("star_name")]
        public string StarName { get; set; }

        [Newtonsoft.Json.JsonProperty("is_factory_built")]
        public bool IsFactoryBuilt { get; set; }

        [Newtonsoft.Json.JsonProperty("total_factories")]
        public int TotalFactories { get; set; }

        [Newtonsoft.Json.JsonProperty("factories")]
        public FactoryEntry[] Factories { get; set; } = Array.Empty<FactoryEntry>();

        [Newtonsoft.Json.JsonProperty("power_generation")]
        public double PowerGeneration { get; set; }

        [Newtonsoft.Json.JsonProperty("power_consumption")]
        public double PowerConsumption { get; set; }
    }

    [Serializable]
    public class FactoryEntry
    {
        [Newtonsoft.Json.JsonProperty("id")]
        public int Id { get; set; }

        [Newtonsoft.Json.JsonProperty("type")]
        public string Type { get; set; }

        [Newtonsoft.Json.JsonProperty("level")]
        public int Level { get; set; }

        [Newtonsoft.Json.JsonProperty("recipe_id")]
        public int RecipeId { get; set; }

        [Newtonsoft.Json.JsonProperty("status")]
        public string Status { get; set; }

        [Newtonsoft.Json.JsonProperty("reason")]
        public string Reason { get; set; }
    }

    [Serializable]
    public class StationEntry
    {
        [Newtonsoft.Json.JsonProperty("station_id")]
        public int StationId { get; set; }

        [Newtonsoft.Json.JsonProperty("station_name")]
        public string StationName { get; set; }

        [Newtonsoft.Json.JsonProperty("planet_name")]
        public string PlanetName { get; set; }

        [Newtonsoft.Json.JsonProperty("slots")]
        public StationSlotEntry[] Slots { get; set; } = Array.Empty<StationSlotEntry>();

        [Newtonsoft.Json.JsonProperty("is_interstellar")]
        public bool IsInterstellar { get; set; }

        [Newtonsoft.Json.JsonProperty("vessel_count")]
        public int VesselCount { get; set; }

        [Newtonsoft.Json.JsonProperty("dock_count")]
        public int DockCount { get; set; }
    }

    [Serializable]
    public class StationSlotEntry
    {
        [Newtonsoft.Json.JsonProperty("item_id")]
        public int ItemId { get; set; }

        [Newtonsoft.Json.JsonProperty("item_name")]
        public string ItemName { get; set; }

        [Newtonsoft.Json.JsonProperty("count")]
        public int Count { get; set; }

        [Newtonsoft.Json.JsonProperty("max_count")]
        public int MaxCount { get; set; }

        [Newtonsoft.Json.JsonProperty("fill_ratio")]
        public double FillRatio { get; set; }
    }

    [Serializable]
    public class RouteEntry
    {
        [Newtonsoft.Json.JsonProperty("station_id")]
        public int StationId { get; set; }

        [Newtonsoft.Json.JsonProperty("station_name")]
        public string StationName { get; set; }

        [Newtonsoft.Json.JsonProperty("planet_name")]
        public string PlanetName { get; set; }

        [Newtonsoft.Json.JsonProperty("item_name")]
        public string ItemName { get; set; }

        [Newtonsoft.Json.JsonProperty("item_id")]
        public int ItemId { get; set; }

        [Newtonsoft.Json.JsonProperty("supply_logic")]
        public int SupplyLogic { get; set; }

        [Newtonsoft.Json.JsonProperty("demand_logic")]
        public int DemandLogic { get; set; }
    }
}
