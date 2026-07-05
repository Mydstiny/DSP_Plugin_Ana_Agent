# WebSocket 通信协议 v0.1.0

## 消息信封

所有消息使用 JSON 格式:

```json
{
  "channel": "alert | snapshot | command",
  "type": "具体消息类型",
  "payload": {},
  "id": "uuid-v4",
  "timestamp": 1712345678
}
```

## Channel: alert

插件 → Companion，实时推送，无回执。

| type | 触发条件 | payload |
|------|---------|---------|
| `power_critical` | 某星球电力 < 20% | `{planet_id, planet_name, ratio, generation, consumption}` |
| `resource_depleted` | 矿脉储量归零 | `{planet_id, planet_name, vein_id, item_id, item_name}` |
| `station_full` | 物流塔输出满仓 | `{station_id, station_name, item_id, item_name, capacity_ratio}` |
| `production_stalled` | 产线停产 > 60s | `{planet_id, planet_name, factory_id, reason}` |

## Channel: snapshot (双向)

### 插件 → Companion

| type | 触发 | payload |
|------|------|---------|
| `periodic_snapshot` | 每 30s 自动 | 见 SnapshotData schema |
| `galaxy_scan_result` | 用户触发扫描 | 见 GalaxyScanResult schema |
| `player_action` | 玩家放置/拆除 | `{action, planet_id, building_type, position}` |

### Companion → 插件

| type | 触发 | payload |
|------|------|---------|
| `task_list_update` | 分析完成 | 见 TaskList schema |
| `agent_progress` | Agent 运行中 | `{phase, phase_name, message, progress_pct}` |
| `task_status_sync` | 任务状态变更回执 | `{task_id, status}` |

## Channel: command (双向)

### 插件 → Companion

| type | payload |
|------|---------|
| `trigger_scan` | `{}` |
| `mode_switch` | `{layer1: bool, layer2: bool}` |
| `dismiss_task` | `{task_id}` |
| `track_task` | `{task_id}` |

### Companion → 插件

| type | payload |
|------|---------|
| `scan_complete` | `{task_count, summary}` |
| `heartbeat` | `{uptime_seconds}` |
| `error` | `{code, message}` |
