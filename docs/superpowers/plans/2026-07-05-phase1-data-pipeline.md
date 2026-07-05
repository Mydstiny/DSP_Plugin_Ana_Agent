# Phase 1: 数据通道 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建从 DSP 游戏内到 Python Companion App 的完整数据通道: Harmony Patch 采集生产数据 → WebSocket Server 推送 → Python Client 接收验证。

**Architecture:** C# BepInEx 插件通过 Harmony Prefix 拦截 `FactoryProductionStat.GameTick`，每 5 秒聚合数据并通过 `System.Net.WebSockets` 推送到端口 8470。Python asyncio 客户端连接、接收 JSON 快照、打印验证。

**Tech Stack:** C# .NET Framework 4.8, BepInEx 5.4.17+, HarmonyX, Newtonsoft.Json, System.Net.WebSockets, Python 3.10+, websockets, pydantic

## Global Constraints

- 所有 Harmony Prefix 必须 try-catch 包裹 — 插件绝不能导致游戏崩溃
- 数据采集不能导致卡顿 — 聚合逻辑 O(1)
- Python >= 3.10, websockets >= 12.0, pydantic >= 2.0
- BepInEx 5.4.17+, .NET Framework 4.8 (Unity 2022.3 兼容)
- WebSocket 端口 8470
- Phase 1 只实现 `/snapshot` channel，类型为 `periodic_snapshot`
- 开发阶段快照间隔 5 秒 (后续改为 30 秒)
- config.yaml 不提交到 git (已在 .gitignore 中)
- 不在 Windows PowerShell 5.1 中运行 C# 构建 — 使用 dotnet CLI

---

## File Map

```
Create: plugin/DSP_AI_Advisor/DSP_AI_Advisor.csproj       — C# 项目文件, 引用 BepInEx + Harmony + Newtonsoft.Json
Create: plugin/DSP_AI_Advisor/Plugin.cs                    — BepInEx 入口, 注册 Harmony + 启动 WebSocket Server
Create: plugin/DSP_AI_Advisor/Models/SnapshotData.cs       — 快照数据模型 (PSCustomObject → JSON)
Create: plugin/DSP_AI_Advisor/DataCollectors/ProductionCollector.cs — Harmony Patch 采集产能数据
Create: plugin/DSP_AI_Advisor/WebSocket/MessageCodec.cs    — JSON 信封编码/解码
Create: plugin/DSP_AI_Advisor/WebSocket/WsServer.cs        — WebSocket Server (端口 8470, /snapshot channel)
Create: companion/src/dsp_ai_advisor/ws_client.py          — Python 异步 WebSocket 客户端
Create: companion/src/dsp_ai_advisor/models.py             — Pydantic 数据模型 (消息信封 + 快照)
Modify: companion/src/dsp_ai_advisor/main.py               — 集成 WS client
Create: companion/tests/test_ws_protocol.py                — WebSocket 协议集成测试
```

---

### Task 1: C# 插件项目骨架

**Files:**
- Create: `plugin/DSP_AI_Advisor/DSP_AI_Advisor.csproj`
- Create: `plugin/DSP_AI_Advisor/Plugin.cs`

**Interfaces:**
- Consumes: 无 (第一个任务)
- Produces: `DSP_AI_Advisor.dll` — BepInEx 插件, 启动时输出日志 "DSP AI Advisor loaded", 注册 Harmony, 启动 WebSocket 服务器 (空壳)

- [ ] **Step 1: 创建 .csproj 文件**

写入 `plugin/DSP_AI_Advisor/DSP_AI_Advisor.csproj`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="15.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Configuration Condition=" '$(Configuration)' == '' ">Debug</Configuration>
    <Platform Condition=" '$(Platform)' == '' ">AnyCPU</Platform>
    <ProjectGuid>{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}</ProjectGuid>
    <OutputType>Library</OutputType>
    <AppDesignerFolder>Properties</AppDesignerFolder>
    <RootNamespace>DSP_AI_Advisor</RootNamespace>
    <AssemblyName>DSP_AI_Advisor</AssemblyName>
    <TargetFrameworkVersion>v4.8</TargetFrameworkVersion>
    <FileAlignment>512</FileAlignment>
    <Deterministic>true</Deterministic>
  </PropertyGroup>

  <PropertyGroup Condition=" '$(Configuration)|$(Platform)' == 'Debug|AnyCPU' ">
    <DebugSymbols>true</DebugSymbols>
    <DebugType>full</DebugType>
    <Optimize>false</Optimize>
    <OutputPath>bin\Debug\</OutputPath>
    <DefineConstants>DEBUG;TRACE</DefineConstants>
    <ErrorReport>prompt</ErrorReport>
    <WarningLevel>4</WarningLevel>
  </PropertyGroup>

  <PropertyGroup Condition=" '$(Configuration)|$(Platform)' == 'Release|AnyCPU' ">
    <DebugType>pdbonly</DebugType>
    <Optimize>true</Optimize>
    <OutputPath>bin\Release\</OutputPath>
    <DefineConstants>TRACE</DefineConstants>
    <ErrorReport>prompt</ErrorReport>
    <WarningLevel>4</WarningLevel>
  </PropertyGroup>

  <!-- DSP Managed DLLs — 需要指向游戏安装目录 -->
  <!-- 构建时通过 -p:DSPManaged="C:\path\to\DSP\Managed" 传入 -->
  <PropertyGroup>
    <DSPManaged Condition=" '$(DSPManaged)' == '' ">C:\Program Files (x86)\Steam\steamapps\common\Dyson Sphere Program\DSPGAME_Data\Managed</DSPManaged>
  </PropertyGroup>

  <ItemGroup>
    <Reference Include="Assembly-CSharp">
      <HintPath>$(DSPManaged)\Assembly-CSharp.dll</HintPath>
      <Private>False</Private>
    </Reference>
    <Reference Include="UnityEngine">
      <HintPath>$(DSPManaged)\UnityEngine.dll</HintPath>
      <Private>False</Private>
    </Reference>
    <Reference Include="UnityEngine.CoreModule">
      <HintPath>$(DSPManaged)\UnityEngine.CoreModule.dll</HintPath>
      <Private>False</Private>
    </Reference>
  </ItemGroup>

  <!-- BepInEx + Harmony NuGet -->
  <ItemGroup>
    <PackageReference Include="BepInEx.BaseLib" Version="5.4.21" />
    <PackageReference Include="HarmonyX" Version="2.10.1" />
    <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
  </ItemGroup>
</Project>
```

- [ ] **Step 2: 创建 Plugin.cs**

写入 `plugin/DSP_AI_Advisor/Plugin.cs`:

```csharp
using System;
using BepInEx;
using BepInEx.Logging;
using HarmonyLib;

namespace DSP_AI_Advisor
{
    [BepInPlugin(PluginInfo.PLUGIN_GUID, PluginInfo.PLUGIN_NAME, PluginInfo.PLUGIN_VERSION)]
    public class Plugin : BaseUnityPlugin
    {
        internal static ManualLogSource Log;

        private Harmony _harmony;

        private void Awake()
        {
            Log = Logger;
            Log.LogInfo($"DSP AI Advisor v{PluginInfo.PLUGIN_VERSION} loading...");

            try
            {
                // 注册 Harmony 补丁
                _harmony = new Harmony(PluginInfo.PLUGIN_GUID);
                _harmony.PatchAll();

                Log.LogInfo("Harmony patches applied successfully.");

                // 启动 WebSocket Server
                WebSocket.WsServer.Instance.Start();

                Log.LogInfo("DSP AI Advisor loaded.");
            }
            catch (Exception ex)
            {
                Log.LogError($"Failed to initialize: {ex}");
            }
        }

        private void OnDestroy()
        {
            WebSocket.WsServer.Instance.Stop();
            _harmony?.UnpatchSelf();
            Log.LogInfo("DSP AI Advisor unloaded.");
        }
    }

    internal static class PluginInfo
    {
        public const string PLUGIN_GUID = "com.dsp.ai.advisor";
        public const string PLUGIN_NAME = "DSP AI Advisor";
        public const string PLUGIN_VERSION = "0.1.0";
    }
}
```

- [ ] **Step 3: 验证 .csproj 格式正确 (不需要 DSP DLLs 在场也能 restore)**

```bash
cd plugin/DSP_AI_Advisor
dotnet restore
```

Expected: "Restore succeeded" 或关于 DSPManaged 路径不存在的 warning (可忽略)

- [ ] **Step 4: Commit**

```bash
cd C:/Users/14288/DSP_Plugin_Ana_Agent
git add plugin/DSP_AI_Advisor/DSP_AI_Advisor.csproj plugin/DSP_AI_Advisor/Plugin.cs
git commit -m "feat(plugin): add BepInEx plugin skeleton with Harmony entry point"
```

---

### Task 2: 数据模型 — SnapshotData

**Files:**
- Create: `plugin/DSP_AI_Advisor/Models/SnapshotData.cs`

**Interfaces:**
- Consumes: Task 1 (Plugin.cs — 项目可编译)
- Produces: `SnapshotData` class — `ToJson()` 返回 JSON string, `ProductionStat` 内部字典

- [ ] **Step 1: 创建数据模型**

写入 `plugin/DSP_AI_Advisor/Models/SnapshotData.cs`:

```csharp
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
```

- [ ] **Step 2: Commit**

```bash
cd C:/Users/14288/DSP_Plugin_Ana_Agent
git add plugin/DSP_AI_Advisor/Models/SnapshotData.cs
git commit -m "feat(plugin): add SnapshotData model with JSON serialization"
```

---

### Task 3: 消息编解码器 — MessageCodec

**Files:**
- Create: `plugin/DSP_AI_Advisor/WebSocket/MessageCodec.cs`

**Interfaces:**
- Consumes: Task 2 (SnapshotData)
- Produces: `MessageCodec.Encode(string channel, string type, object payload) -> string` — 封装为协议信封 JSON; `MessageCodec.EncodeSnapshot(SnapshotData data) -> string` — 便捷方法

- [ ] **Step 1: 创建编解码器**

写入 `plugin/DSP_AI_Advisor/WebSocket/MessageCodec.cs`:

```csharp
using System;
using Newtonsoft.Json;

namespace DSP_AI_Advisor.WebSocket
{
    /// <summary>
    /// WebSocket 消息信封编解码 — 遵循 shared/protocol.md v0.1.0.
    /// </summary>
    public static class MessageCodec
    {
        /// <summary>
        /// 封装为协议信封: { channel, type, payload, id, timestamp }
        /// </summary>
        public static string Encode(string channel, string type, object payload)
        {
            var envelope = new
            {
                channel,
                type,
                payload,
                id = Guid.NewGuid().ToString(),
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds()
            };

            return JsonConvert.SerializeObject(envelope, Formatting.None);
        }

        /// <summary>
        /// 便捷方法 — 编码 SnapshotData 为 snapshot channel 消息.
        /// </summary>
        public static string EncodeSnapshot(Models.SnapshotData data)
        {
            return Encode("snapshot", "periodic_snapshot", data);
        }

        /// <summary>
        /// 解码消息信封, 提取 channel/type/payload.
        /// 返回 null 表示解析失败.
        /// </summary>
        public static MessageEnvelope Decode(string rawJson)
        {
            try
            {
                return JsonConvert.DeserializeObject<MessageEnvelope>(rawJson);
            }
            catch (Exception)
            {
                return null;
            }
        }
    }

    [Serializable]
    public class MessageEnvelope
    {
        [JsonProperty("channel")]
        public string Channel { get; set; }

        [JsonProperty("type")]
        public string Type { get; set; }

        [JsonProperty("payload")]
        public string Payload { get; set; }  // raw JSON string

        [JsonProperty("id")]
        public string Id { get; set; }

        [JsonProperty("timestamp")]
        public long Timestamp { get; set; }
    }
}
```

- [ ] **Step 2: Commit**

```bash
cd C:/Users/14288/DSP_Plugin_Ana_Agent
git add plugin/DSP_AI_Advisor/WebSocket/MessageCodec.cs
git commit -m "feat(plugin): add WebSocket message codec (encode/decode envelope)"
```

---

### Task 4: WebSocket Server

**Files:**
- Create: `plugin/DSP_AI_Advisor/WebSocket/WsServer.cs`

**Interfaces:**
- Consumes: Task 2 (SnapshotData), Task 3 (MessageCodec)
- Produces: `WsServer` singleton — `Start()`, `Stop()`, `BroadcastSnapshot(SnapshotData)`, 监听 `http://localhost:8470/`, 接受 WebSocket 连接, 维护已连接 client 列表, 广播快照

- [ ] **Step 1: 创建 WebSocket Server**

写入 `plugin/DSP_AI_Advisor/WebSocket/WsServer.cs`:

```csharp
using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace DSP_AI_Advisor.WebSocket
{
    /// <summary>
    /// WebSocket Server — 监听端口 8470, 向所有已连接 client 广播快照数据.
    /// 单例模式, 在独立线程上运行 HttpListener.
    /// </summary>
    public class WsServer
    {
        private static readonly Lazy<WsServer> _instance =
            new(() => new WsServer());

        public static WsServer Instance => _instance.Value;

        private readonly ConcurrentBag<System.Net.WebSockets.WebSocket> _clients = new();
        private HttpListener _listener;
        private CancellationTokenSource _cts;
        private Task _listenTask;

        public const int Port = 8470;
        public bool IsRunning { get; private set; }

        private WsServer() { }

        /// <summary>
        /// 启动 WebSocket 服务器.
        /// </summary>
        public void Start()
        {
            if (IsRunning) return;

            try
            {
                _listener = new HttpListener();
                _listener.Prefixes.Add($"http://localhost:{Port}/");
                _listener.Start();

                _cts = new CancellationTokenSource();
                _listenTask = Task.Run(() => ListenLoop(_cts.Token));

                IsRunning = true;
                Plugin.Log.LogInfo($"[WsServer] Listening on ws://localhost:{Port}/");
            }
            catch (HttpListenerException ex) when (ex.ErrorCode == 5)
            {
                // 权限不足 — Windows 需要 URL ACL
                Plugin.Log.LogWarning(
                    $"[WsServer] Port {Port} requires admin permission. " +
                    $"Run once as admin: netsh http add urlacl url=http://+:{Port}/ user=Everyone");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[WsServer] Failed to start: {ex.Message}");
            }
        }

        /// <summary>
        /// 停止 WebSocket 服务器.
        /// </summary>
        public void Stop()
        {
            if (!IsRunning) return;

            try
            {
                _cts?.Cancel();

                // 关闭所有 client 连接
                foreach (var client in _clients)
                {
                    try { client.CloseAsync(WebSocketCloseStatus.NormalClosure, "Server shutting down", CancellationToken.None).Wait(1000); }
                    catch { /* best effort */ }
                }

                _listener?.Stop();
                _listener?.Close();
                IsRunning = false;

                Plugin.Log.LogInfo("[WsServer] Stopped.");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[WsServer] Error during stop: {ex.Message}");
            }
        }

        /// <summary>
        /// 向所有已连接 client 广播文本消息.
        /// </summary>
        public void Broadcast(string message)
        {
            if (_clients.IsEmpty) return;

            var buffer = Encoding.UTF8.GetBytes(message);
            var segment = new ArraySegment<byte>(buffer);

            foreach (var client in _clients)
            {
                if (client.State != WebSocketState.Open) continue;
                try
                {
                    client.SendAsync(segment, WebSocketMessageType.Text, true, CancellationToken.None)
                          .Wait(100);  // 100ms timeout — 不阻塞游戏线程
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning($"[WsServer] Broadcast failed for a client: {ex.Message}");
                }
            }
        }

        /// <summary>
        /// 广播 SnapshotData.
        /// </summary>
        public void BroadcastSnapshot(Models.SnapshotData data)
        {
            var json = MessageCodec.EncodeSnapshot(data);
            Broadcast(json);
        }

        /// <summary>
        /// 主监听循环 — 接受连接, 升级到 WebSocket, 加入 client 列表.
        /// </summary>
        private async Task ListenLoop(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var context = await _listener.GetContextAsync();
                    if (ct.IsCancellationRequested) break;

                    if (context.Request.IsWebSocketRequest)
                    {
                        // 异步处理 WebSocket 握手 (fire-and-forget)
                        _ = HandleClientAsync(context, ct);
                    }
                    else
                    {
                        context.Response.StatusCode = 400;
                        context.Response.Close();
                    }
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (HttpListenerException)
                {
                    break;  // listener stopped
                }
                catch (Exception ex)
                {
                    if (!ct.IsCancellationRequested)
                        Plugin.Log.LogWarning($"[WsServer] Accept error: {ex.Message}");
                }
            }
        }

        private async Task HandleClientAsync(HttpListenerContext context, CancellationToken ct)
        {
            System.Net.WebSockets.WebSocket ws = null;
            try
            {
                var wsContext = await context.AcceptWebSocketAsync(null);
                ws = wsContext.WebSocket;
                _clients.Add(ws);

                Plugin.Log.LogInfo($"[WsServer] Client connected. Total: {_clients.Count}");

                // 保持连接直到 client 断开
                var buffer = new byte[4096];
                while (ws.State == WebSocketState.Open && !ct.IsCancellationRequested)
                {
                    try
                    {
                        var result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                        if (result.MessageType == WebSocketMessageType.Close)
                            break;
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[WsServer] Client handler error: {ex.Message}");
            }
            finally
            {
                if (ws != null)
                {
                    try { await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "Done", CancellationToken.None); }
                    catch { /* best effort */ }
                }
                // 从 client 列表中移除 — ConcurrentBag 不支持 Remove, 重建
                RemoveClient(ws);
                Plugin.Log.LogInfo($"[WsServer] Client disconnected. Total: {_clients.Count}");
            }
        }

        private void RemoveClient(System.Net.WebSockets.WebSocket target)
        {
            var remaining = new ConcurrentBag<System.Net.WebSockets.WebSocket>();
            foreach (var client in _clients)
            {
                if (client != target)
                    remaining.Add(client);
            }
            // 替换 — ConcurrentBag 不支持原子替换, 但 Accept 已序列化, 安全
            while (_clients.TryTake(out _)) { }
            foreach (var client in remaining)
                _clients.Add(client);
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
cd C:/Users/14288/DSP_Plugin_Ana_Agent
git add plugin/DSP_AI_Advisor/WebSocket/WsServer.cs
git commit -m "feat(plugin): add WebSocket server (port 8470, client broadcast)"
```

---

### Task 5: ProductionCollector — Harmony Patch

**Files:**
- Create: `plugin/DSP_AI_Advisor/DataCollectors/ProductionCollector.cs`
- Modify: `plugin/DSP_AI_Advisor/Plugin.cs` (已创建 — 无需修改, Harmony.PatchAll() 自动发现)

**Interfaces:**
- Consumes: Task 2 (SnapshotData), Task 4 (WsServer.BroadcastSnapshot)
- Produces: `ProductionCollector` — HarmonyPatch on `FactoryProductionStat.GameTick`, 每 300 ticks (5 秒) 聚合数据并广播

- [ ] **Step 1: 创建 ProductionCollector**

写入 `plugin/DSP_AI_Advisor/DataCollectors/ProductionCollector.cs`:

```csharp
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
```

- [ ] **Step 2: Commit**

```bash
cd C:/Users/14288/DSP_Plugin_Ana_Agent
git add plugin/DSP_AI_Advisor/DataCollectors/ProductionCollector.cs
git commit -m "feat(plugin): add ProductionCollector Harmony patch (5s snapshot)"
```

---

### Task 6: Python 数据模型

**Files:**
- Create: `companion/src/dsp_ai_advisor/models.py`

**Interfaces:**
- Consumes: Task 1-5 (C# 端定义的消息格式)
- Produces: Pydantic models — `MessageEnvelope`, `ItemStat`, `SnapshotSummary`, `SnapshotData`

- [ ] **Step 1: 创建 Pydantic 数据模型**

写入 `companion/src/dsp_ai_advisor/models.py`:

```python
"""Pydantic data models matching the WebSocket protocol and C# SnapshotData."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ItemStat(BaseModel):
    """Single item production stat within a snapshot."""
    item_id: int
    item_name: str
    produced: int
    consumed: int
    net: int
    rate_per_min: float


class SnapshotSummary(BaseModel):
    """Aggregate summary of a snapshot."""
    total_items_tracked: int
    items_in_deficit: int
    items_in_surplus: int


class SnapshotData(BaseModel):
    """Periodic production snapshot payload."""
    snapshot_id: str
    game_tick: int
    elapsed_seconds: float
    timestamp_unix: int
    production: dict[str, ItemStat] = Field(default_factory=dict)
    summary: SnapshotSummary | None = None


class MessageEnvelope(BaseModel):
    """Top-level WebSocket message envelope."""
    channel: str
    type: str
    payload: dict | None = None
    id: str
    timestamp: int
```

- [ ] **Step 2: Commit**

```bash
cd C:/Users/14288/DSP_Plugin_Ana_Agent
git add companion/src/dsp_ai_advisor/models.py
git commit -m "feat(companion): add Pydantic data models for protocol messages"
```

---

### Task 7: Python WebSocket 客户端

**Files:**
- Create: `companion/src/dsp_ai_advisor/ws_client.py`
- Modify: `companion/src/dsp_ai_advisor/main.py` (集成 WS client)

**Interfaces:**
- Consumes: Task 6 (models.py)
- Produces: `DspWsClient` class — `connect()`, `disconnect()`, `on_snapshot` callback, 自动重连

- [ ] **Step 1: 创建 WebSocket 客户端**

写入 `companion/src/dsp_ai_advisor/ws_client.py`:

```python
"""Async WebSocket client — connects to the C# plugin's WsServer on port 8470."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Awaitable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from .models import MessageEnvelope, SnapshotData

logger = logging.getLogger(__name__)

# Callback type: async function receiving SnapshotData
SnapshotCallback = Callable[[SnapshotData], Awaitable[None]]


class DspWsClient:
    """WebSocket client for the DSP AI Advisor plugin.

    Connects to ws://localhost:8470, receives snapshot messages,
    parses them through pydantic, and dispatches to registered callbacks.
    """

    def __init__(self, host: str = "localhost", port: int = 8470) -> None:
        self._url = f"ws://{host}:{port}"
        self._connection: ClientConnection | None = None
        self._running = False
        self._reconnect_task: asyncio.Task | None = None

        # Registered callbacks
        self._snapshot_callbacks: list[SnapshotCallback] = []

    @property
    def is_connected(self) -> bool:
        """Whether the WebSocket connection is currently open."""
        return self._connection is not None and self._connection.state.name == "OPEN"

    def on_snapshot(self, callback: SnapshotCallback) -> SnapshotCallback:
        """Register a callback for snapshot messages. Can be used as decorator."""
        self._snapshot_callbacks.append(callback)
        return callback

    async def connect(self) -> None:
        """Connect to the WebSocket server and start the message loop."""
        if self._running:
            logger.warning("Already running")
            return

        self._running = True
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def disconnect(self) -> None:
        """Disconnect and stop reconnection attempts."""
        self._running = False

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        if self._connection:
            try:
                await self._connection.close()
            except Exception:
                pass
            self._connection = None

        logger.info("Disconnected.")

    async def _reconnect_loop(self) -> None:
        """Auto-reconnect with exponential backoff (1s → 2s → 4s → ... → 30s max)."""
        backoff = 1.0
        max_backoff = 30.0

        while self._running:
            try:
                logger.info("Connecting to %s ...", self._url)
                async with websockets.connect(self._url) as ws:
                    self._connection = ws
                    logger.info("Connected to %s", self._url)
                    backoff = 1.0  # reset on success

                    await self._message_loop(ws)

            except (OSError, websockets.ConnectionClosed) as e:
                logger.warning("Connection lost: %s. Reconnecting in %.0fs...", e, backoff)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in connection loop")

            if not self._running:
                break

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    async def _message_loop(self, ws: ClientConnection) -> None:
        """Receive messages and dispatch to handlers."""
        async for raw in ws:
            if not self._running:
                break

            try:
                data = json.loads(raw)
                envelope = MessageEnvelope(**data)
                await self._dispatch(envelope)
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON: %.100s", raw)
            except Exception:
                logger.exception("Error handling message")

    async def _dispatch(self, envelope: MessageEnvelope) -> None:
        """Route message to the appropriate handler based on channel/type."""
        if envelope.channel == "snapshot" and envelope.type == "periodic_snapshot":
            if envelope.payload:
                snapshot = SnapshotData(**envelope.payload)
                logger.info(
                    "Snapshot #%s: tick=%d, %d items tracked (%d deficit, %d surplus)",
                    snapshot.snapshot_id,
                    snapshot.game_tick,
                    snapshot.summary.total_items_tracked if snapshot.summary else 0,
                    snapshot.summary.items_in_deficit if snapshot.summary else 0,
                    snapshot.summary.items_in_surplus if snapshot.summary else 0,
                )
                for callback in self._snapshot_callbacks:
                    try:
                        await callback(snapshot)
                    except Exception:
                        logger.exception("Error in snapshot callback")
        else:
            logger.debug("Ignored message: channel=%s type=%s", envelope.channel, envelope.type)
```

- [ ] **Step 2: 集成到 main.py**

修改 `companion/src/dsp_ai_advisor/main.py`:

```python
"""DSP AI Advisor Companion App — Entry Point."""

import asyncio
import logging
import signal
import sys

from .ws_client import DspWsClient
from .models import SnapshotData

logger = logging.getLogger(__name__)


async def _on_snapshot(snapshot: SnapshotData) -> None:
    """Example callback — just log with more detail."""
    if snapshot.summary and snapshot.summary.items_in_deficit > 0:
        deficit_items = [
            (item_id, stat)
            for item_id, stat in snapshot.production.items()
            if stat.net < 0
        ]
        for item_id, stat in deficit_items[:5]:  # top 5
            logger.info(
                "  DEFICIT %s (#%s): net=%d, rate=%.1f/min",
                stat.item_name, item_id, stat.net, stat.rate_per_min,
            )


async def main_async() -> None:
    """Main async entry point."""
    logger.info("DSP AI Advisor Companion v%s starting...", __import__("dsp_ai_advisor").__version__)

    client = DspWsClient(host="localhost", port=8470)
    client.on_snapshot(_on_snapshot)

    await client.connect()

    # Keep running until interrupted
    stop = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutting down...")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop.wait()

    await client.disconnect()
    logger.info("Goodbye.")


def main() -> None:
    """Console script entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
cd C:/Users/14288/DSP_Plugin_Ana_Agent
git add companion/src/dsp_ai_advisor/ws_client.py companion/src/dsp_ai_advisor/main.py
git commit -m "feat(companion): add async WebSocket client with auto-reconnect"
```

---

### Task 8: WebSocket 协议集成测试

**Files:**
- Create: `companion/tests/test_ws_protocol.py`

**Interfaces:**
- Consumes: Task 6 (models.py), Task 7 (ws_client.py)
- Produces: 独立测试 — 启动本地 WebSocket echo server, 验证消息编解码和客户端的解析逻辑

- [ ] **Step 1: 创建测试**

写入 `companion/tests/test_ws_protocol.py`:

```python
"""Integration tests for WebSocket protocol — message encode/decode round-trip."""

import asyncio
import json

import pytest
import websockets
from websockets.asyncio.server import serve

from dsp_ai_advisor.models import MessageEnvelope, SnapshotData, ItemStat, SnapshotSummary


# ── 测试数据工厂 ──────────────────────────────────────────

def make_sample_snapshot() -> SnapshotData:
    """Create a SnapshotData matching the C# plugin output format."""
    return SnapshotData(
        snapshot_id="a1b2c3d4",
        game_tick=72000,
        elapsed_seconds=5.0,
        timestamp_unix=1712345678,
        production={
            "1001": ItemStat(
                item_id=1001,
                item_name="铁矿",
                produced=1200,
                consumed=1100,
                net=100,
                rate_per_min=240.0,
            ),
            "1101": ItemStat(
                item_id=1101,
                item_name="铁块",
                produced=800,
                consumed=950,
                net=-150,
                rate_per_min=160.0,
            ),
        },
        summary=SnapshotSummary(
            total_items_tracked=2,
            items_in_deficit=1,
            items_in_surplus=1,
        ),
    )


def make_envelope(snapshot: SnapshotData) -> dict:
    """Encode a snapshot as a protocol envelope (matching C# MessageCodec.EncodeSnapshot)."""
    return {
        "channel": "snapshot",
        "type": "periodic_snapshot",
        "payload": json.loads(snapshot.model_dump_json()),
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": 1712345678,
    }


# ── 消息模型测试 ──────────────────────────────────────────

class TestMessageModels:
    """Verify pydantic models parse correctly."""

    def test_snapshotdata_from_json(self):
        """SnapshotData should parse from a protocol envelope's payload."""
        snap = make_sample_snapshot()
        envelope = make_envelope(snap)

        parsed = SnapshotData(**envelope["payload"])
        assert parsed.snapshot_id == "a1b2c3d4"
        assert parsed.game_tick == 72000
        assert len(parsed.production) == 2
        assert parsed.summary.items_in_deficit == 1
        assert parsed.production["1101"].item_name == "铁块"
        assert parsed.production["1101"].net == -150

    def test_message_envelope_parsing(self):
        """MessageEnvelope should parse a full protocol message."""
        snap = make_sample_snapshot()
        raw = json.dumps(make_envelope(snap))

        parsed = MessageEnvelope(**json.loads(raw))
        assert parsed.channel == "snapshot"
        assert parsed.type == "periodic_snapshot"
        assert parsed.payload is not None

    def test_empty_snapshot(self):
        """Snapshot with no production data should still parse."""
        snap = SnapshotData(
            snapshot_id="empty",
            game_tick=0,
            elapsed_seconds=0,
            timestamp_unix=0,
        )
        assert snap.production == {}
        assert snap.summary is None


# ── WebSocket 集成测试 ────────────────────────────────────

class TestWsRoundTrip:
    """End-to-end: server sends envelope → client receives and parses."""

    @pytest.mark.asyncio
    async def test_send_receive_snapshot(self, unused_tcp_port: int):
        """Client connects, server sends a snapshot envelope, client parses it."""
        snap = make_sample_snapshot()
        envelope = make_envelope(snap)
        client_received: list[SnapshotData] = []

        async def _echo_server(ws):
            # Send one envelope then close
            await ws.send(json.dumps(envelope))
            await ws.close()

        async with serve(_echo_server, "localhost", unused_tcp_port) as server:
            async with websockets.connect(
                f"ws://localhost:{unused_tcp_port}"
            ) as ws:
                raw = await ws.recv()
                data = json.loads(raw)
                msg = MessageEnvelope(**data)
                assert msg.channel == "snapshot"
                parsed = SnapshotData(**msg.payload)
                client_received.append(parsed)

        assert len(client_received) == 1
        result = client_received[0]
        assert result.snapshot_id == "a1b2c3d4"
        assert result.production["1001"].item_name == "铁矿"
        assert result.production["1101"].net == -150

    @pytest.mark.asyncio
    async def test_multiple_clients(self, unused_tcp_port: int):
        """Server can send to multiple connected clients."""
        snap = make_sample_snapshot()
        envelope = json.dumps(make_envelope(snap))
        received_counts = [0, 0]

        async def _broadcast_server(ws):
            # Broadcast same message to each connecting client
            for _ in range(2):
                await ws.send(envelope)
            await ws.close()

        async def _client(idx: int):
            async with websockets.connect(
                f"ws://localhost:{unused_tcp_port}"
            ) as ws:
                raw = await ws.recv()
                data = json.loads(raw)
                msg = MessageEnvelope(**data)
                assert msg.channel == "snapshot"
                received_counts[idx] += 1

        # Use a server that handles each client sequentially (broadcast pattern)
        # For this test, we use a simpler approach: one server, two sequential connections
        server_task = asyncio.create_task(
            _run_sequential_server(unused_tcp_port, envelope, 2)
        )
        await asyncio.sleep(0.1)

        await asyncio.gather(_client(0), _client(1))
        await server_task

        assert received_counts == [1, 1]


async def _run_sequential_server(port: int, message: str, count: int):
    """Accept `count` clients sequentially, send `message` to each."""
    async def _handler(ws):
        await ws.send(message)
        await ws.close()

    async with serve(_handler, "localhost", port) as s:
        await asyncio.sleep(5)  # keep alive long enough


# ── 序列化一致性测试 ───────────────────────────────────────

class TestSerializationConsistency:
    """Ensure Python and C# produce compatible JSON."""

    def test_snapshot_json_format_matches_csharp(self):
        """Python SnapshotData JSON should match the C# JsonProperty names."""
        snap = make_sample_snapshot()
        raw = snap.model_dump_json()

        data = json.loads(raw)
        # C# uses camelCase via JsonProperty attributes
        assert "snapshot_id" in data
        assert "game_tick" in data
        assert "elapsed_seconds" in data
        assert "timestamp_unix" in data
        assert "production" in data
        assert "summary" in data
        # ItemStat fields
        stat = data["production"]["1001"]
        assert "item_id" in stat
        assert "item_name" in stat
        assert "produced" in stat
        assert "consumed" in stat
        assert "net" in stat
        assert "rate_per_min" in stat

    def test_envelope_format_matches_csharp(self):
        """Envelope JSON should match C# MessageCodec output."""
        snap = make_sample_snapshot()
        envelope = make_envelope(snap)
        raw = json.dumps(envelope)

        data = json.loads(raw)
        assert "channel" in data
        assert "type" in data
        assert "payload" in data
        assert "id" in data
        assert "timestamp" in data
```

- [ ] **Step 2: 运行测试**

```bash
cd companion
pip install -e ".[dev]"
pytest tests/test_ws_protocol.py -v
```

Expected: 8 tests PASS

- [ ] **Step 3: Commit**

```bash
cd C:/Users/14288/DSP_Plugin_Ana_Agent
git add companion/tests/test_ws_protocol.py
git commit -m "test(companion): add WebSocket protocol round-trip tests"
```

---

### Task 9: 端到端验证 (E2E)

**Manual verification** — 因为依赖实际的 DSP 游戏和 BepInEx 环境,此任务为手动验证步骤,不需要代码变更。

**Files:**
- 无新建/修改文件

**Interfaces:**
- Consumes: All previous tasks

- [ ] **Step 1: 准备 DSP 测试环境**

1. 确认 DSP 游戏已安装
2. 确认 BepInEx 5.x 已安装到 DSP 目录
3. 构建插件:

```bash
cd plugin/DSP_AI_Advisor

# 设置 DSPManaged 指向游戏 Managed 目录
$dspManaged = "C:\Program Files (x86)\Steam\steamapps\common\Dyson Sphere Program\DSPGAME_Data\Managed"

dotnet build -c Debug -p:DSPManaged="$dspManaged"
```

Expected: Build succeeded.

- [ ] **Step 2: 部署插件**

复制构建产物到 DSP BepInEx plugins 目录:

```bash
$dspBepInEx = "C:\Program Files (x86)\Steam\steamapps\common\Dyson Sphere Program\BepInEx\plugins\DSP_AI_Advisor"
mkdir $dspBepInEx -Force
copy plugin\DSP_AI_Advisor\bin\Debug\net48\DSP_AI_Advisor.dll $dspBepInEx\
# 同时复制依赖的 DLL (Newtonsoft.Json 等)
copy plugin\DSP_AI_Advisor\bin\Debug\net48\*.dll $dspBepInEx\
```

- [ ] **Step 3: 启动 Companion App**

在另一个终端:

```bash
cd companion
pip install -e .
python -m dsp_ai_advisor
```

Expected: "Connecting to ws://localhost:8470 ..." (此时还未连接,等游戏启动)

- [ ] **Step 4: 启动游戏并验证数据流**

1. 启动 Dyson Sphere Program
2. 加载一个有产线活动的存档
3. 观察 Companion App 终端输出

Expected 输出示例:

```
2026-07-05 14:30:01 [INFO] dsp_ai_advisor.ws_client: Connected to ws://localhost:8470
2026-07-05 14:30:06 [INFO] dsp_ai_advisor.ws_client: Snapshot #a1b2c3d4: tick=36000, 12 items tracked (3 deficit, 5 surplus)
2026-07-05 14:30:06 [INFO] dsp_ai_advisor.main:   DEFICIT 铁块 (#1101): net=-150, rate=160.0/min
2026-07-05 14:30:11 [INFO] dsp_ai_advisor.ws_client: Snapshot #e5f6g7h8: tick=36300, 14 items tracked (2 deficit, 7 surplus)
```

- [ ] **Step 5: 验证 BepInEx 日志**

检查 `BepInEx\LogOutput.log` 或控制台输出:

Expected:

```
[Info   : DSP AI Advisor] DSP AI Advisor v0.1.0 loading...
[Info   : DSP AI Advisor] Harmony patches applied successfully.
[Info   : DSP AI Advisor] [WsServer] Listening on ws://localhost:8470/
[Info   : DSP AI Advisor] DSP AI Advisor loaded.
[Info   : DSP AI Advisor] [WsServer] Client connected. Total: 1
```

---

## Milestone M1 Checklist

- [x] C# 插件骨架 (BepInEx + Harmony 环境搭建) — Task 1
- [x] 数据模型 (SnapshotData, JSON 序列化) — Task 2
- [x] 消息编解码器 (协议信封) — Task 3
- [x] WebSocket Server (端口 8470, client 广播) — Task 4
- [x] ProductionCollector (Harmony Patch, 5s 快照) — Task 5
- [x] Python 数据模型 (Pydantic) — Task 6
- [x] Python WS Client (异步连接 + 自动重连) — Task 7
- [x] 协议测试 (8 tests, pytest) — Task 8
- [ ] E2E 验证 (真机 DSP 运行 + Companion 接收数据) — Task 9

**M1 通过标准**: 在 Companion App 终端中看到游戏产线数据的实时快照输出。
