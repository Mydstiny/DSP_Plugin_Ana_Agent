# DSP AI Advisor — 设计规格书

> 戴森球计划 AI 产线优化插件
>
> 版本: 0.1.0 | 日期: 2026-07-05 | 状态: 设计完成

---

## 1. 项目概述

### 1.1 目标

为《戴森球计划》构建一个 AI 驱动的产线分析与优化插件，能够:

1. **实时监控** 全星系产线/电力/物流状态
2. **AI 深度分析** 识别瓶颈、闲置、低效产线
3. **生成优化任务清单** 直接显示在游戏 UI 中
4. **玩家可操作** 追踪、执行、忽略任务

### 1.2 核心价值

玩家不再需要在统计面板和外部计算器之间来回切换。AI 自动完成分析，告诉玩家"去哪里、做什么"，以游戏内任务清单的方式呈现。

---

## 2. 架构概览

```
Dyson Sphere Program (Unity 2022.3)
┌─────────────────────────────────────────────────┐
│  BepInEx Plugin (C# .NET Framework 4.8)          │
│                                                   │
│  Data Collectors  →  Alert Engine  →  UI System  │
│  (Harmony Patch)      (本地规则)       (UGUI)     │
│                                                   │
│         │                │                ▲       │
│         ▼                ▼                │       │
│  ┌──────────────────────────────────────────┐    │
│  │  WebSocket Server (端口 8470)            │    │
│  │  /alert  │  /snapshot  │  /command      │    │
│  └──────────┴─────────────┴────────────────┘    │
└─────────────────────────────────────────────────┘
         │                │                │
         ▼                ▼                ▲
┌─────────────────────────────────────────────────┐
│  AI Advisor Companion (Python 3.10+)             │
│                                                   │
│  WS Client  →  Rule Engine  →  LLM Pipeline     │
│                          →  Agent (6-Phase)      │
│                          →  Task Manager         │
│                                                   │
│  System Tray GUI (PySide6, 可选)                  │
└─────────────────────────────────────────────────┘
```

### 2.1 组件清单

| ID | 组件 | 归属 | 语言 | 职责 |
|----|------|------|------|------|
| C1 | DataCollectors | C# 插件 | C# | Harmony 补丁采集 Factory/Power/Logistics/Tech 数据 |
| C2 | AlertEngine | C# 插件 | C# | 本地规则检测紧急状态 (电力<20%/原料归零/产线停产) |
| C3 | WebSocketServer | C# 插件 | C# | 3 channel: /alert (推送), /snapshot (双向), /command (双向) |
| C4 | TaskListSidebar | C# 插件 | C# | 任务清单侧边栏 UI, 按优先级/类型分组, 支持追踪/忽略 |
| C5 | PlanetHUD | C# 插件 | C# | 星球视图建筑标注覆盖层, 颜色编码问题类型 |
| C6 | ControlPanel | C# 插件 | C# | 控制面板: 实时告警开关/快照开关/Provider 切换/触发扫描 |
| C7 | WSClient | Python Companion | Python | 异步 WebSocket 客户端 (asyncio + websockets) |
| C8 | RuleEngine | Python Companion | Python | 产能配平/物料平衡/升级扫描/星球专业化分析 |
| C9 | LLMPipeline | Python Companion | Python | 可插拔 LLM Provider, 统一 OpenAI-compatible 接口 |
| C10 | OptimizationAgent | Python Companion | Python | 6-Phase 专属 Agent, 8 个 Tool, Chain-of-Thought 推理 |
| C11 | TaskManager | Python Companion | Python | 任务去重/排序/生命周期管理 |
| C12 | SystemTray | Python Companion | Python | 可选系统托盘 GUI: 连接状态/日志/配置 |

---

## 3. 数据采集设计

### 3.1 采集维度

| 维度 | Harmony Patch 目标 | 频率 | 内容 |
|------|---------------------|------|------|
| 产能统计 | `FactoryProductionStat.GameTick` | 每 tick → 聚合 1s | productRegister/consumeRegister |
| 电力系统 | `PowerSystem.GameTick` | 每 1s | 发电/耗电/蓄电/各星球电力 |
| 物流网络 | `StationComponent.GameTick` | 每 2s | 塔库存/航线运力/传送带饱和度 |
| 科技进度 | `GameMain.history.techStates` | 每 30s | 已解锁科技/当前研究/升级等级 |
| 星球工厂 | `PlanetFactory.GameTick` | 每 30s | 建筑统计/矿脉储量/闲置机器 |

### 3.2 全星系扫描 (Galaxy Scan)

手动触发的一次性深度扫描，提供逐建筑/逐产线/逐星球的完整数据:

- 所有工厂建筑清单 (类型/位置/配方/状态)
- 所有传送带网络与连接关系
- 所有物流塔 (库存/槽位配置/运输船状态)
- 矿脉覆盖与储量
- 电力设施详情
- 闲置机器统计 (缺料/满仓/停电)
- 所有星际航线 (起点/终点/货物/运力)
- 星球/物流塔命名
- 科技树状态

扫描为异步执行 (1-3 秒)，不阻塞游戏主线程。

### 3.3 数据流

```
Game Tick → Harmony Prefix → AlertBuffer → WebSocket /alert (实时)
                           → SnapshotBuffer → WebSocket /snapshot (30s聚合)
                           
用户触发 → GalaxyScan → 全量 JSON → WebSocket /snapshot (galaxy_scan_result)
```

---

## 4. WebSocket 通信协议

### 4.1 消息信封

```json
{
  "channel": "alert | snapshot | command",
  "type": "具体消息类型",
  "payload": {},
  "id": "uuid",
  "timestamp": 1712345678
}
```

### 4.2 Channel 定义

#### /alert (插件 → Companion, 实时推送)

| type | 触发条件 | payload |
|------|---------|---------|
| `power_critical` | 某星球电力 < 20% | `{planet, ratio, generation, consumption}` |
| `resource_depleted` | 矿脉储量归零 | `{planet, vein_id, item}` |
| `station_full` | 物流塔输出满仓 | `{station_id, item, capacity_ratio}` |
| `production_stalled` | 产线停产 > 60s | `{planet, factory_id, reason}` |

#### /snapshot (双向)

**插件 → Companion:**

| type | 触发 | payload |
|------|------|---------|
| `periodic_snapshot` | 每 30s 自动 | 全量统计 JSON |
| `galaxy_scan_result` | 用户触发全星系扫描 | 全量静态数据 JSON |
| `player_action` | 玩家放置/拆除建筑 | `{action, planet, building_type, position}` |

**Companion → 插件:**

| type | 触发 | payload |
|------|------|---------|
| `task_list_update` | 分析完成后 | 任务清单数组 |
| `agent_progress` | Agent 分析进行中 | `{phase, message, progress_pct}` |
| `single_task_complete` | 玩家完成某任务 | 任务状态更新回执 |

#### /command (双向控制)

| 方向 | type | 含义 |
|------|------|------|
| 插件→Companion | `trigger_scan` | 用户点击"全星系分析" |
| 插件→Companion | `mode_switch` | `{layer1: on/off, layer2: on/off}` |
| 插件→Companion | `dismiss_task` | 用户忽略某条任务 |
| Companion→插件 | `scan_complete` | 分析结束,附带摘要 |
| Companion→插件 | `heartbeat` | 连接存活确认 (每 5s) |

---

## 5. AI 分析引擎

### 5.1 双层架构

| 层级 | 引擎 | 触发 | 延迟 | 用途 |
|------|------|------|------|------|
| Layer 1 (实时) | C# AlertEngine (规则) | 每 tick | <1ms | 紧急告警 (电力/原料/停产) |
| Layer 2 (深度) | Python OptimizationAgent (LLM) | 手动触发/定时 | 10-60s | 产能/物流/升级/星球专业化分析 |

### 5.2 OptimizationAgent: 6-Phase 推理链

```
Phase 1: 全局概览
  ├─ 扫描所有星球产线状态
  ├─ 识别产能利用率低下的星球/产线
  └─ 输出: 问题星球排行榜

Phase 2: 瓶颈根因分析
  ├─ 追溯每个闲置产线的根因
  ├─ 分类: 缺原料/满产物/电力不足/物流卡顿
  └─ 输出: 每个问题的根因 + 影响范围

Phase 3: 星际物流优化
  ├─ 分析航线运力利用率
  ├─ 发现冗余/低效航线
  ├─ 建议物流塔分组和命名方案
  └─ 输出: 优化后的物流拓扑

Phase 4: 产能配平计算
  ├─ 基于目标产物逆向计算原料需求
  ├─ 发现配平缺口
  └─ 输出: 具体建筑数量调整方案

Phase 5: 升级建议
  ├─ 扫描可用科技升级
  ├─ 评估升级收益 (传送带/分拣器/工厂/配方)
  └─ 输出: 优先级排序的升级清单

Phase 6: 任务拆解
  ├─ 将优化建议拆成可执行步骤
  ├─ 标注: 星球/位置/操作类型/预估耗时/优先级
  └─ 输出: 结构化任务清单 → 推送到游戏 UI
```

### 5.3 Agent Toolbox (8 个工具)

| # | 工具名 | 参数 | 描述 |
|---|--------|------|------|
| T1 | `scan_planet_production` | `planet_id: int` | 扫描指定星球所有产线,返回每台机器的配方/状态/利用率/闲置原因 |
| T2 | `analyze_production_chain` | `item_name, target_rate` | 逆向计算所需原料和中间产物工厂数量 |
| T3 | `audit_logistics_routes` | — | 审计所有星际航线,返回运力利用率/空驶率/瓶颈航线 |
| T4 | `check_tech_upgrades` | — | 扫描当前科技等级,列出所有可用的建筑/配方升级及收益 |
| T5 | `calculate_power_balance` | — | 计算各星球电力供需,识别过剩/短缺星球 |
| T6 | `suggest_station_grouping` | `planet_id: int` | 分析物流塔命名/分组现状,给出统一命名规范和组织建议 |
| T7 | `find_idle_factories` | `min_idle_ratio: float` | 全局扫描闲置工厂,按根因分类统计并定位具体建筑 |
| T8 | `generate_task_breakdown` | `optimization_plan: str` | 将优化建议拆解为玩家可执行的步骤序列 |

### 5.4 LLM Provider 抽象层

统一使用 OpenAI-compatible chat completions 格式作为内部 IR:

```python
class BaseProvider(ABC):
    async def chat(self, messages: list[dict], tools: list[dict] | None) -> Response
    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]

class AnthropicProvider(BaseProvider):    # Anthropic SDK → IR
class OpenAICompatProvider(BaseProvider):  # OpenAI / DeepSeek / Ollama / 自定义
```

**配置文件 (config.yaml):**

```yaml
llm:
  default: claude
  providers:
    claude:
      provider_type: anthropic
      api_key: ${ANTHROPIC_API_KEY}
      model: claude-sonnet-5
    openai:
      provider_type: openai_compat
      base_url: https://api.openai.com/v1
      api_key: ${OPENAI_API_KEY}
      model: gpt-5
    deepseek:
      provider_type: openai_compat
      base_url: https://api.deepseek.com/v1
      api_key: ${DEEPSEEK_API_KEY}
      model: deepseek-v4-pro
    custom_1:
      provider_type: openai_compat
      base_url: http://localhost:11434/v1
      api_key: ollama
      model: qwen3:14b
    custom_2:
      provider_type: openai_compat
      base_url: https://your-proxy.com/v1
      api_key: ${CUSTOM_API_KEY}
      model: your-model
```

Agent 默认使用 `llm.default` 指定的 provider，控制面板可运行时切换。

---

## 6. 游戏内 UI

### 6.1 控制面板

- 位置: 游戏右上角, 可拖拽
- 内容:
  - Layer 1 (实时告警) 开关
  - Layer 2 (周期快照) 开关
  - AI Provider 选择 (下拉: 已配置的 provider 列表)
  - "全星系分析" 按钮 (触发 Galaxy Scan + Agent)
  - 上次分析时间和结果数量
  - 设置按钮 (打开配置面板)
  - 暂停 Companion (断开 WebSocket)

### 6.2 任务清单侧边栏

- 位置: 屏幕右侧, 可展开/收起
- 分组: 🔴紧急 → 🟡产能 → 🔵物流 → 🟢升级
- 每条任务展示:
  - 图标 (Lucide: `AlertTriangle`/`Gauge`/`Ship`/`ArrowUpCircle`)
  - 标题 (一句话描述)
  - 详情 (根因 + 建议操作 + 位置)
  - 操作按钮: `[追踪]` `[忽略]`
- 追踪模式: 点击追踪后, 星球视图自动跳转并高亮目标建筑
- 任务状态: 新建 / 进行中 (被追踪) / 已解决 (数据验证) / 已忽略

### 6.3 星球 HUD 标注

- 星球视图上直接标注问题建筑:
  - 🔴 红色脉冲: 电力不足/停产
  - 🟡 黄色标记: 闲置/低利用率
  - 🔵 蓝色标记: 物流问题
- 鼠标悬停显示问题摘要
- 点击跳转到任务清单对应条目

### 6.4 图标方案

统一使用 **Lucide** 图标库 (MIT 开源, 统一设计语言):

| 用途 | Lucide 图标 |
|------|------------|
| 紧急告警 | `AlertTriangle` |
| 产能分析 | `Gauge` |
| 物流优化 | `Ship` |
| 升级建议 | `ArrowUpCircle` |
| 电力 | `Zap` |
| 任务清单 | `ListChecks` |
| 全星系扫描 | `ScanSearch` |
| 控制面板 | `SlidersHorizontal` |
| 设置 | `Settings` |
| 追踪 | `Crosshair` |
| 忽略 | `EyeOff` |
| 已完成 | `CheckCircle2` |
| 连接状态-在线 | `Wifi` |
| 连接状态-离线 | `WifiOff` |
| Companion 状态 | `Server` |

---

## 7. 错误处理

### 7.1 分层策略

| 层级 | 策略 | 降级路径 |
|------|------|---------|
| Harmony Patch | try-catch 包裹所有 Prefix, 异常记日志 | 跳过本 tick, 不影响游戏 |
| WebSocket Server | 端口冲突检测, 启动失败提示用户 | 插件 UI 显示"离线模式" |
| WebSocket Client | 自动重连 + 指数退避 (1s→2s→4s→...→max 30s) | 断连期间任务清单显示最后已知状态 |
| Rule Engine | 输入验证, 异常输入跳过 | 产出空结果, 不阻塞 Agent |
| LLM Call | 重试 3 次 → 降级 | 云端失败 → 规则引擎结果; 全部失败 → 提示用户 |
| Agent | 30s 超时终止单个 Phase | Phase 失败 → 跳过, 继续下一 Phase, 最后汇总已完成部分 |
| UI | 所有渲染 try-catch | 单个控件异常不影响其他控件 |

### 7.2 不可妥协的底线

- **插件绝不能导致游戏崩溃** — 所有 Harmony 补丁必须是 try-catch 包裹
- **数据采集不能导致卡顿** — 所有采集逻辑必须是 O(1) 或 O(n) 且 n 可控
- **Agent 失败不丢扫描数据** — 扫描结果写入 SQLite 缓存

---

## 8. 测试策略

| 层级 | 方式 | 覆盖重点 |
|------|------|---------|
| C# DataCollectors | DSP 真机测试 | 数据采集正确性, 不卡顿不崩溃 |
| C# WebSocketServer | 单元测试 + 真机 | 消息序列化, 端口冲突, 多 client |
| C# UI | 真机测试 | 渲染正确, 交互响应 |
| Python RuleEngine | pytest | 产能计算, 配平公式, 阈值判断 |
| Python LLMPipeline | pytest + mock | Provider 切换, API 错误处理, 重试逻辑 |
| Python Agent | mock tools + 真 API | 推理链正确性, 工具调用逻辑, 超时处理 |
| Python TaskManager | pytest | 去重/排序/生命周期 |
| WebSocket 协议 | pytest-asyncio | 消息序列化/反序列化, 断连重连 |
| 端到端 | DSP + Companion 同时运行 | 扫描→Agent分析→任务推送→UI渲染 全链路 |

---

## 9. 项目结构

```
DSP_Plugin_Ana_Agent/
├── README.md
├── config.yaml.example              # LLM Provider 配置模板
│
├── plugin/                          # BepInEx C# 插件
│   ├── DSP_AI_Advisor.sln
│   └── DSP_AI_Advisor/
│       ├── DSP_AI_Advisor.csproj
│       ├── Plugin.cs                # BepInEx 入口
│       ├── DataCollectors/
│       │   ├── ProductionCollector.cs
│       │   ├── PowerCollector.cs
│       │   ├── LogisticsCollector.cs
│       │   ├── TechCollector.cs
│       │   └── GalaxyScanner.cs     # 全星系扫描
│       ├── AlertEngine/
│       │   ├── AlertRule.cs
│       │   └── AlertRules.cs        # 规则集合
│       ├── WebSocket/
│       │   ├── WsServer.cs
│       │   ├── MessageCodec.cs      # JSON 序列化/反序列化
│       │   └── ChannelHandler.cs
│       ├── UI/
│       │   ├── ControlPanel.cs
│       │   ├── TaskListSidebar.cs
│       │   ├── PlanetHUD.cs
│       │   └── Icons.cs             # Lucide 图标引用
│       └── Models/
│           ├── SnapshotData.cs
│           ├── AlertEvent.cs
│           └── TaskItem.cs
│
├── companion/                       # Python Companion App
│   ├── pyproject.toml
│   ├── src/
│   │   └── dsp_ai_advisor/
│   │       ├── __init__.py
│   │       ├── main.py              # 入口
│   │       ├── ws_client.py         # WebSocket 客户端
│   │       ├── rule_engine/
│   │       │   ├── __init__.py
│   │       │   ├── production.py    # 产能配平
│   │       │   ├── power.py         # 电力分析
│   │       │   ├── logistics.py     # 物流分析
│   │       │   └── upgrades.py      # 升级扫描
│   │       ├── llm/
│   │       │   ├── __init__.py
│   │       │   ├── base.py          # BaseProvider 抽象
│   │       │   ├── anthropic_provider.py
│   │       │   ├── openai_compat_provider.py
│   │       │   └── config.py        # config.yaml 加载
│   │       ├── agent/
│   │       │   ├── __init__.py
│   │       │   ├── agent.py         # OptimizationAgent 主逻辑
│   │       │   ├── tools.py         # 8 个 Tool 实现
│   │       │   └── prompts.py       # System Prompt 模板
│   │       ├── task_manager/
│   │       │   ├── __init__.py
│   │       │   ├── manager.py       # 任务去重/排序/生命周期
│   │       │   └── models.py        # Task 数据模型
│   │       └── storage/
│   │           ├── __init__.py
│   │           └── db.py            # SQLite 操作
│   ├── tests/
│   │   ├── test_rule_engine.py
│   │   ├── test_llm_pipeline.py
│   │   ├── test_agent.py
│   │   ├── test_task_manager.py
│   │   └── test_ws_protocol.py
│   └── config.yaml
│
├── shared/                          # 跨组件共享定义
│   ├── protocol.md                  # WebSocket 协议文档
│   ├── item_ids.json                # DSP 物品 ID 映射表
│   └── recipe_data.json             # DSP 配方数据
│
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-07-05-dsp-ai-advisor-design.md
```

---

## 10. 开发阶段

### Phase 1: 数据通道 (MVP 基础)

- [x] 设计文档
- [ ] C# 插件骨架 (BepInEx + Harmony 环境搭建)
- [ ] ProductionCollector (Harmony Patch `FactoryProductionStat.GameTick`)
- [ ] WebSocket Server 基础 (端口 8470, `/snapshot` channel)
- [ ] Python Companion 骨架 (asyncio + websockets)
- [ ] WS Client 连接 + 快照接收验证
- [ ] **里程碑 M1**: 游戏数据成功导出到 Companion App

### Phase 2: 分析引擎

- [ ] Rule Engine 基础规则 (产能配平/电力检查/升级扫描)
- [ ] LLM Pipeline (Anthropic + OpenAI-compat Provider)
- [ ] OptimizationAgent (6-Phase + 8 Tools)
- [ ] Task Manager (去重/排序/生命周期)
- [ ] Galaxy Scanner (全星系深度扫描)
- [ ] **里程碑 M2**: Agent 产出第一份优化任务清单

### Phase 3: 游戏内 UI

- [ ] ControlPanel UI
- [ ] TaskListSidebar UI
- [ ] PlanetHUD 标注
- [ ] UI ↔ WebSocket 交互 (任务追踪/忽略/完成)
- [ ] Agent 进度显示
- [ ] **里程碑 M3**: 游戏内完整交互闭环

### Phase 4: 打磨

- [ ] 实时告警 (Layer 1 AlertEngine)
- [ ] System Tray GUI (可选)
- [ ] 端到端测试 + 真机稳定性
- [ ] 配置文件 + UI 设置面板
- [ ] README + 安装指南
- [ ] **里程碑 M4**: 可发布 beta 版本

---

## 11. 技术依赖

### C# 插件
- BepInEx 5.4.17+
- HarmonyX (通过 BepInEx)
- .NET Framework 4.8 (Unity 2022.3 兼容)
- `System.Net.WebSockets` (内置)

### Python Companion
- Python 3.10+
- `websockets` (WebSocket)
- `anthropic` (Anthropic SDK)
- `openai` (OpenAI SDK, 同时用于兼容 DeepSeek/Ollama/自定义)
- `pyyaml` (配置)
- `pydantic` (数据模型)
- `aiosqlite` (SQLite 异步)
- (可选) `pyside6` (System Tray GUI)
- (可选) `langchain`/`langgraph` (Agent 编排)

### 开发工具
- DevEco Studio / Visual Studio / Rider (C#)
- pytest + pytest-asyncio (Python 测试)
- Thunderstore CLI (发布)
