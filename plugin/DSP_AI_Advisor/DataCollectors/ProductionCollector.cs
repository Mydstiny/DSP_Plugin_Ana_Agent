using System;
using System.Collections.Generic;
using DSP_AI_Advisor.Models;
using HarmonyLib;

namespace DSP_AI_Advisor.DataCollectors
{
    /// <summary>
    /// Harmony Patch — 拦截 FactoryProductionStat.GameTick 采集产能数据.
    ///
    /// 方法签名 (来自 DSP 反编译):
    ///   public void GameTick(GameStatData gameStatData, long time,
    ///       int[] productRegister, int[] consumeRegister,
    ///       long[] productServedRegister, long[] consumeServedRegister)
    ///
    /// productRegister[i] = item i 本 tick 产量
    /// consumeRegister[i] = item i 本 tick 消耗量
    /// </summary>
    [HarmonyPatch]
    public static class ProductionCollector
    {
        /// <summary>
        /// 聚合缓冲区 — key: itemId, value: (produced, consumed)
        /// </summary>
        private static readonly Dictionary<int, (long Produced, long Consumed)> Accumulator = new();

        /// <summary>
        /// 上次快照时的 game tick.
        /// </summary>
        private static long _lastSnapshotTick = 0;

        /// <summary>
        /// 快照间隔 (ticks). 60 ticks/秒 × 5 秒 = 300 ticks.
        /// </summary>
        private const long SNAPSHOT_INTERVAL_TICKS = 300;

        /// <summary>
        /// 跟踪 item 名称 — itemId → itemName.
        /// </summary>
        private static readonly Dictionary<int, string> ItemNames = new();

        /// <summary>
        /// 定义 Patch 目标 — 运行时查找 FactoryProductionStat.GameTick.
        /// 使用 AccessTools.TypeByName 而非 typeof() 因为 Assembly-CSharp 是 Private=False 引用.
        /// </summary>
        public static System.Reflection.MethodBase TargetMethod()
        {
            return AccessTools.Method(
                AccessTools.TypeByName("FactoryProductionStat"),
                "GameTick");
        }

        /// <summary>
        /// Harmony Prefix — 在原始 GameTick 之前执行.
        /// 匹配原始方法签名: GameTick(GameStatData, long, int[], int[], long[], long[])
        /// 只需前 4 个参数 (后 2 个 serveRegister 暂不使用).
        /// </summary>
        [HarmonyPrefix]
        public static void Prefix(
            object __instance,
            long time,
            int[] productRegister,
            int[] consumeRegister)
        {
            try
            {
                if (productRegister == null || consumeRegister == null) return;

                // 聚合到缓冲区
                int len = Math.Min(productRegister.Length, consumeRegister.Length);
                for (int i = 0; i < len; i++)
                {
                    int p = productRegister[i];
                    int c = consumeRegister[i];

                    // 跳过无活动的 item (绝大多数 item 在任意时刻都是 0)
                    if (p == 0 && c == 0) continue;

                    lock (Accumulator)
                    {
                        if (Accumulator.TryGetValue(i, out var existing))
                        {
                            Accumulator[i] = (existing.Produced + p, existing.Consumed + c);
                        }
                        else
                        {
                            Accumulator[i] = (p, c);
                        }
                    }
                }

                // 检查是否到了快照时间
                long ticksSinceLast = time - _lastSnapshotTick;
                if (ticksSinceLast >= SNAPSHOT_INTERVAL_TICKS || _lastSnapshotTick == 0)
                {
                    BuildAndSendSnapshot(time, ticksSinceLast);
                    _lastSnapshotTick = time;
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[ProductionCollector] Error in Prefix: {ex.Message}");
                // 不重新抛出 — 绝不影响游戏运行
            }
        }

        /// <summary>
        /// 构建 SnapshotData, 清空缓冲区, 广播.
        /// </summary>
        private static void BuildAndSendSnapshot(long gameTick, long elapsedTicks)
        {
            Dictionary<int, (long, long)> snapshot;
            lock (Accumulator)
            {
                // 复制并清空
                snapshot = new Dictionary<int, (long, long)>(Accumulator);
                Accumulator.Clear();
            }

            if (snapshot.Count == 0) return;  // 没有活动产线, 不发空快照

            var data = new SnapshotData
            {
                GameTick = gameTick,
                ElapsedSeconds = elapsedTicks / 60.0,
                TimestampUnix = DateTimeOffset.UtcNow.ToUnixTimeSeconds()
            };

            int deficitCount = 0;
            int surplusCount = 0;

            foreach (var kvp in snapshot)
            {
                int itemId = kvp.Key;
                long produced = kvp.Value.Item1;
                long consumed = kvp.Value.Item2;
                long net = produced - consumed;
                double ratePerMin = (produced / (elapsedTicks / 60.0)) * 60.0;

                if (!ItemNames.TryGetValue(itemId, out var itemName))
                {
                    itemName = $"Item_{itemId}";
                }

                data.Production[itemId] = new ItemStat
                {
                    ItemId = itemId,
                    ItemName = itemName,
                    Produced = produced,
                    Consumed = consumed,
                    RatePerMin = Math.Round(ratePerMin, 1)
                };

                if (net < 0) deficitCount++;
                if (net > 0) surplusCount++;
            }

            data.Summary = new SnapshotSummary
            {
                TotalItemsTracked = data.Production.Count,
                ItemsInDeficit = deficitCount,
                ItemsInSurplus = surplusCount
            };

            WebSocket.WsServer.Instance.BroadcastSnapshot(data);
        }
    }
}
