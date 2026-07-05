using System;
using System.Collections.Generic;
using Newtonsoft.Json;

namespace DSP_AI_Advisor.Models
{
    /// <summary>
    /// 单个物品的产能统计 — 聚合周期内的产量和消耗量.
    /// </summary>
    [Serializable]
    public class ItemStat
    {
        [JsonProperty("item_id")]
        public int ItemId { get; set; }

        [JsonProperty("item_name")]
        public string ItemName { get; set; }

        [JsonProperty("produced")]
        public long Produced { get; set; }

        [JsonProperty("consumed")]
        public long Consumed { get; set; }

        [JsonProperty("net")]
        public long Net => Produced - Consumed;

        [JsonProperty("rate_per_min")]
        public double RatePerMin { get; set; }
    }

    /// <summary>
    /// 周期产能快照 — 每 N 秒聚合一次, 通过 WebSocket /snapshot 推送.
    /// </summary>
    [Serializable]
    public class SnapshotData
    {
        [JsonProperty("snapshot_id")]
        public string SnapshotId { get; set; } = Guid.NewGuid().ToString("N")[..8];

        [JsonProperty("game_tick")]
        public long GameTick { get; set; }

        [JsonProperty("elapsed_seconds")]
        public double ElapsedSeconds { get; set; }

        [JsonProperty("timestamp_unix")]
        public long TimestampUnix { get; set; }

        [JsonProperty("production")]
        public Dictionary<int, ItemStat> Production { get; set; } = new();

        [JsonProperty("summary")]
        public SnapshotSummary Summary { get; set; } = new();
    }

    [Serializable]
    public class SnapshotSummary
    {
        [JsonProperty("total_items_tracked")]
        public int TotalItemsTracked { get; set; }

        [JsonProperty("items_in_deficit")]
        public int ItemsInDeficit { get; set; }

        [JsonProperty("items_in_surplus")]
        public int ItemsInSurplus { get; set; }
    }
}
