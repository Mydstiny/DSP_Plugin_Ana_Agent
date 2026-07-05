# DSP AI Advisor — 戴森球计划 AI 产线优化插件

> 用 AI 分析产线状态，生成优化任务清单，直接显示在游戏中。

[![Phase](https://img.shields.io/badge/phase-4%20(polish)-blue)](#)
[![Tests](https://img.shields.io/badge/tests-20%2F20%20PASS-brightgreen)](#)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 功能

- 🔍 **实时数据采集** — 自动采集产线/电力/物流/科技数据
- 🤖 **AI 深度分析** — 专属 Agent (6 阶段推理 + 8 个工具) 分析瓶颈、闲置产线、物流效率
- 📋 **游戏内任务清单** — 优化建议在游戏中显示为可追踪/忽略的任务
- 🔌 **可插拔 AI** — 支持 Claude / GPT / DeepSeek / Ollama / 自定义 API
- ⚡ **实时告警** — 电力不足/原料耗尽/物流阻塞即时通知

## 架构

```
Dyson Sphere Program (Unity 2022.3)
├── BepInEx C# 插件
│   ├── Harmony Patch: FactoryProductionStat / PowerSystem
│   ├── WebSocket Server (端口 8470)
│   ├── 控制面板 / 任务清单 / 星球 HUD (F8 打开)
│   └── AlertEngine — 实时告警推送
│
└── Python Companion App
    ├── 规则引擎 — 本地即时分析
    ├── OptimizationAgent — 6-Phase LLM Agent + 8 Tools
    ├── 可插拔 LLM Provider (Claude/GPT/DeepSeek/自定义)
    └── Task Manager — 去重/排序/生命周期
```

## 安装

### 前置条件

- **戴森球计划** (Steam)
- **BepInEx 5.4.17+** — [安装指南](https://thunderstore.io/c/dyson-sphere-program/p/BepInEx/BepInExPack/)
- **Python 3.10+**
- **.NET SDK 8.0** (仅插件构建需要)

### 1. 构建 C# 插件

```bash
cd plugin/DSP_AI_Advisor

# 设置游戏路径
$dspManaged = "C:\Program Files (x86)\Steam\steamapps\common\Dyson Sphere Program\DSPGAME_Data\Managed"

dotnet build -c Release -p:DSPManaged="$dspManaged"
```

### 2. 部署插件

```bash
# 复制 DLL 到 BepInEx plugins 目录
$bep = "C:\Program Files (x86)\Steam\steamapps\common\Dyson Sphere Program\BepInEx\plugins\DSP_AI_Advisor"
mkdir $bep -Force
copy bin\Release\net48\*.dll $bep\
```

### 3. 安装 Companion App

```bash
cd companion
pip install -e .
cp config.yaml.example config.yaml
```

### 4. 配置 AI Provider

编辑 `companion/config.yaml`:

```yaml
llm:
  default: deepseek
  providers:
    deepseek:
      provider_type: openai_compat
      base_url: https://api.deepseek.com/v1
      api_key: sk-your-key-here
      model: deepseek-v4-pro
```

### 5. 启动

```bash
# 终端 1: 启动 Companion
cd companion
python -m dsp_ai_advisor

# 终端 2: 启动游戏
# 进入游戏后按 F8 打开控制面板
```

## 使用

| 操作 | 快捷键/按钮 |
|------|-----------|
| 打开控制面板 | F8 |
| 触发全星系分析 | 控制面板 → "Start Full Galaxy Analysis" |
| 查看任务清单 | 控制面板 → "Task List" |
| 追踪任务 | 任务清单 → "Track" |
| 忽略任务 | 任务清单 → "Ignore" |
| 切换星球 HUD | 控制面板 → "Planet HUD" |

## 开发

### 项目结构

```
DSP_Plugin_Ana_Agent/
├── plugin/                    # BepInEx C# 插件
│   └── DSP_AI_Advisor/
│       ├── Plugin.cs          # 入口
│       ├── DataCollectors/    # 数据采集 (Harmony Patch)
│       ├── AlertEngine/       # 实时告警
│       ├── WebSocket/         # WS Server + MessageRouter
│       ├── UI/                # IMGUI 面板
│       └── Models/            # 数据模型
│
├── companion/                 # Python Companion App
│   └── src/dsp_ai_advisor/
│       ├── main.py            # 入口
│       ├── ws_client.py       # WebSocket 客户端
│       ├── llm/               # LLM Provider 抽象层
│       ├── rule_engine/       # 本地规则引擎
│       ├── agent/             # OptimizationAgent
│       ├── task_manager/      # 任务管理
│       └── storage/           # SQLite 持久化
│
├── shared/                    # 跨组件共享
├── config.yaml.example        # 配置模板
└── docs/                      # 设计文档
```

### 运行测试

```bash
cd companion
pytest tests/ -v
```

### 发布到 Thunderstore

```bash
cd plugin
# 打包为 Thunderstore 格式
# 使用 tcli 上传
```

## 许可证

MIT

## 致谢

- [BepInEx](https://github.com/BepInEx/BepInEx) — Unity 游戏 mod 框架
- [Harmony](https://github.com/pardeike/Harmony) — .NET 运行时补丁
- [DSP Planner Export](https://thunderstore.io/c/dyson-sphere-program/p/Suite/DSP_Planner_Export/) — 数据采集方案参考
- [Anthropic](https://www.anthropic.com/) / [DeepSeek](https://deepseek.com/) — LLM API
