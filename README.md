# DSP AI Advisor — 戴森球计划 AI 产线优化插件

> 用 AI 分析产线状态，生成优化任务清单，直接显示在游戏中。

## 架构

```
Dyson Sphere Program (Unity)
├── BepInEx C# 插件 — 数据采集 + 游戏内 UI
│   ├── Harmony Patch: FactoryProductionStat / PowerSystem / Logistics
│   ├── WebSocket Server (端口 8470)
│   ├── 控制面板 / 任务清单侧边栏 / 星球 HUD
└── Python Companion App — AI 分析引擎
    ├── 规则引擎 (本地即时分析)
    ├── OptimizationAgent (6-Phase LLM Agent + 8 Tools)
    ├── 可插拔 LLM Provider (Claude/GPT/DeepSeek/自定义)
    └── Task Manager (去重/排序/生命周期)
```

## 快速开始

### 1. 安装 BepInEx

在戴森球计划中安装 BepInEx 5.4.17+

### 2. 构建 C# 插件

```bash
cd plugin/DSP_AI_Advisor
dotnet build -c Release
# 复制 DLL 到 BepInEx/plugins/
```

### 3. 运行 Companion App

```bash
cd companion
pip install -e .
cp config.yaml.example config.yaml
# 编辑 config.yaml 填入 API Key
python -m dsp_ai_advisor
```

### 4. 启动游戏

插件自动连接 Companion App。F8 打开控制面板。

## 项目结构

```
DSP_Plugin_Ana_Agent/
├── plugin/          # BepInEx C# 插件
├── companion/       # Python Companion App
├── shared/          # 跨组件共享定义 (协议/物品ID/配方)
├── config.yaml.example
└── docs/            # 设计文档
```

## License

MIT
