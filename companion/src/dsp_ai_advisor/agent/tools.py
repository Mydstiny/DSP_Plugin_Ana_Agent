"""Tool definitions and implementations for the DSP Optimization Agent."""

from __future__ import annotations

import json
from typing import Any

from ..rule_engine.production import (
    calculate_production_balance,
    trace_deficit_root_cause,
)
from ..rule_engine.power import analyze_power, calculate_power_recommendation
from ..rule_engine.logistics import analyze_routes, suggest_grouping
from ..rule_engine.upgrades import scan_available_upgrades


# ── Tool Schemas (OpenAI function-calling format) ────────────────────

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "scan_planet_production",
            "description": "扫描指定星球的所有产线，返回每台机器的类型/配方/状态/利用率/闲置原因",
            "parameters": {
                "type": "object",
                "properties": {
                    "planet_id": {
                        "type": "integer",
                        "description": "星球ID",
                    }
                },
                "required": ["planet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_production_chain",
            "description": "给定目标产物和期望产量(/min)，逆向计算所需上游原料和中间产物工厂数量",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "目标产物名称",
                    },
                    "target_rate": {
                        "type": "number",
                        "description": "目标产量 (items/min)",
                    },
                },
                "required": ["item_name", "target_rate"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "audit_logistics_routes",
            "description": "审计所有星际航线，返回每条航线的运力利用率/空驶率，以及物流塔库存状态",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_tech_upgrades",
            "description": "扫描当前科技等级和可用建筑升级，评估每种升级的收益（传送带/分拣器/工厂/配方）",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_power_balance",
            "description": "计算各星球电力供需，识别过剩/短缺星球，给出具体建电建议",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_station_grouping",
            "description": "分析指定星球上物流塔的命名和分组现状，给出统一命名规范和组织建议",
            "parameters": {
                "type": "object",
                "properties": {
                    "planet_id": {
                        "type": "integer",
                        "description": "星球ID",
                    }
                },
                "required": ["planet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_idle_factories",
            "description": "全局扫描闲置工厂（利用率低于阈值），按根因分类统计并定位具体建筑位置",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_idle_ratio": {
                        "type": "number",
                        "description": "最低闲置率阈值 (0.0-1.0)，默认 0.3 表示利用率<70%的工厂",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_task_breakdown",
            "description": "将一条优化建议拆解为玩家可执行的步骤序列，每步包含位置/操作/预期效果",
            "parameters": {
                "type": "object",
                "properties": {
                    "optimization_plan": {
                        "type": "string",
                        "description": "优化建议的完整描述",
                    }
                },
                "required": ["optimization_plan"],
            },
        },
    },
]


# ── Context for tool execution ──────────────────────────────────────

class AgentContext:
    """Context passed to tool functions during Agent execution."""

    def __init__(self, scan_data: dict[str, Any]) -> None:
        self.scan_data = scan_data
        self.recipe_data: dict[int, dict[str, Any]] = {}
        self._load_recipes()

    def _load_recipes(self) -> None:
        """Load recipe data from scan or shared file."""
        recipes = self.scan_data.get("recipes", {})
        if isinstance(recipes, dict):
            for key, val in recipes.items():
                try:
                    self.recipe_data[int(key)] = val
                except (ValueError, TypeError):
                    pass


# ── Tool Implementations ────────────────────────────────────────────

async def scan_planet_production(args: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """T1: Scan a specific planet's production lines."""
    planet_id = args.get("planet_id", 0)

    for planet in ctx.scan_data.get("planets", []):
        if planet.get("planet_id") == planet_id:
            factories = planet.get("factories", [])
            # Summarize by type
            by_type: dict[str, list[dict]] = {}
            for f in factories:
                ftype = f.get("type", "unknown")
                by_type.setdefault(ftype, []).append(f)

            summary = {}
            for ftype, items in by_type.items():
                active = sum(1 for i in items if i.get("status") == "active")
                idle = len(items) - active
                summary[ftype] = {
                    "total": len(items),
                    "active": active,
                    "idle": idle,
                    "utilization": round(active / len(items), 2) if items else 0,
                }

            return {
                "planet_id": planet_id,
                "planet_name": planet.get("planet_name", "Unknown"),
                "total_factories": len(factories),
                "by_type": summary,
                "idle_factories": [
                    {
                        "id": f.get("id"),
                        "type": f.get("type"),
                        "status": f.get("status"),
                        "reason": f.get("reason", "unknown"),
                    }
                    for f in factories
                    if f.get("status") != "active"
                ],
            }

    return {"error": f"Planet {planet_id} not found in scan data"}


async def analyze_production_chain(args: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """T2: Back-calculate production chain requirements."""
    item_name = args.get("item_name", "")
    target_rate = float(args.get("target_rate", 60.0))

    # Find the recipe for this item
    recipes = ctx.recipe_data
    target_recipe = None
    for _, recipe in recipes.items():
        outputs = recipe.get("outputs", [])
        for out in outputs:
            if out.get("item_name", "").lower() == item_name.lower():
                target_recipe = recipe
                break
        if target_recipe:
            break

    if not target_recipe:
        return {
            "item": item_name,
            "error": f"No recipe found for '{item_name}'",
            "suggestion": f"Check if '{item_name}' is a raw resource or if recipe data is available.",
        }

    # Calculate
    output_per_cycle = target_recipe.get("output_count", 1)
    cycle_time = target_recipe.get("time", 1.0)  # seconds
    output_rate_per_machine = (output_per_cycle / cycle_time) * 60.0  # items/min per machine
    machines_needed = target_rate / max(output_rate_per_machine, 0.001)

    inputs_needed = []
    for inp in target_recipe.get("inputs", []):
        input_rate_per_machine = (inp.get("count", 1) / cycle_time) * 60.0
        total_input_rate = input_rate_per_machine * machines_needed
        inputs_needed.append({
            "item_name": inp.get("item_name", "Unknown"),
            "rate_per_min": round(total_input_rate, 1),
        })

    return {
        "item": item_name,
        "target_rate_per_min": target_rate,
        "recipe": target_recipe.get("name", "Unknown"),
        "output_per_machine_per_min": round(output_rate_per_machine, 1),
        "machines_needed": round(machines_needed, 1),
        "inputs_required": inputs_needed,
    }


async def audit_logistics_routes(args: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """T3: Audit all interstellar logistics routes."""
    issues = analyze_routes(ctx.scan_data)
    return {
        "total_routes": len(ctx.scan_data.get("routes", [])),
        "total_stations": len(ctx.scan_data.get("stations", [])),
        "issues": [
            {
                "station": i.station_name,
                "planet": i.planet_name,
                "type": i.issue_type,
                "description": i.description,
                "utilization": round(i.current_utilization, 2),
            }
            for i in issues
        ],
    }


async def check_tech_upgrades(args: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """T4: Scan available tech upgrades."""
    opportunities = scan_available_upgrades(ctx.scan_data)
    return {
        "unlocked_tech": list(ctx.scan_data.get("unlocked_tech", []))[:20],
        "upgrade_opportunities": [
            {
                "type": o.building_type,
                "planet": o.planet_name,
                "current_level": o.current_level,
                "max_level": o.max_level,
                "count": o.count,
                "benefit": o.benefit,
                "priority": o.priority,
            }
            for o in opportunities
        ],
    }


async def calculate_power_balance(args: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """T5: Calculate power balance across all planets."""
    issues = analyze_power(ctx.scan_data)
    return {
        "planets": [
            {
                "planet_id": i.planet_id,
                "planet_name": i.planet_name,
                "generation_mw": i.generation,
                "consumption_mw": i.consumption,
                "surplus_mw": i.surplus,
                "satisfaction": i.satisfaction,
                "severity": i.severity,
                "recommendation": calculate_power_recommendation(i),
            }
            for i in issues
        ],
    }


async def suggest_station_grouping(args: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """T6: Suggest station naming/grouping for a planet."""
    planet_id = args.get("planet_id", 0)
    planet_name = "Unknown"
    for p in ctx.scan_data.get("planets", []):
        if p.get("planet_id") == planet_id:
            planet_name = p.get("planet_name", "Unknown")
            break

    suggestions = suggest_grouping(planet_name, ctx.scan_data)
    return {
        "planet_id": planet_id,
        "planet_name": planet_name,
        "suggestions": [
            {
                "current_name": s.current_name,
                "suggested_name": s.suggested_name,
                "reason": s.reason,
            }
            for s in suggestions
        ],
    }


async def find_idle_factories(args: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """T7: Find idle factories globally."""
    min_idle_ratio = float(args.get("min_idle_ratio", 0.3))

    idle_list: list[dict[str, Any]] = []
    by_planet: dict[str, dict[str, Any]] = {}
    by_cause: dict[str, int] = {}

    for planet in ctx.scan_data.get("planets", []):
        planet_id = planet.get("planet_id", 0)
        planet_name = planet.get("planet_name", "Unknown")
        factories = planet.get("factories", [])

        if not factories:
            continue

        active = sum(1 for f in factories if f.get("status") == "active")
        total = len(factories)
        idle_ratio = (total - active) / max(total, 1)

        if idle_ratio >= min_idle_ratio:
            idle_items = [
                {
                    "id": f.get("id"),
                    "type": f.get("type"),
                    "reason": f.get("reason", "unknown"),
                }
                for f in factories
                if f.get("status") != "active"
            ]

            by_planet[str(planet_id)] = {
                "planet_name": planet_name,
                "total_factories": total,
                "active": active,
                "idle": total - active,
                "idle_ratio": round(idle_ratio, 2),
                "idle_details": idle_items,
            }

            for item in idle_items:
                cause = item.get("reason", "unknown")
                by_cause[cause] = by_cause.get(cause, 0) + 1

            idle_list.append({
                "planet_id": planet_id,
                "planet_name": planet_name,
                "total": total,
                "active": active,
                "idle": total - active,
                "idle_ratio": round(idle_ratio, 2),
            })

    return {
        "planets_with_idle_factories": len(by_planet),
        "by_cause_breakdown": by_cause,
        "detailed": by_planet,
        "summary": sorted(idle_list, key=lambda x: x["idle_ratio"], reverse=True),
    }


async def generate_task_breakdown(args: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """T8: Generate executable task breakdown from optimization plan."""
    plan = args.get("optimization_plan", "")

    # This tool is called by the LLM to format its output.
    # The actual breakdown is done by the LLM — this function just validates
    # and wraps the plan into the task list format.
    return {
        "original_plan": plan,
        "status": "received",
        "message": (
            "优化建议已接收。请基于此建议生成最终的结构化任务清单，"
            "每条任务格式为：{title, category, priority, planet, suggested_action, estimated_effort}"
        ),
    }


# ── Tool dispatcher ─────────────────────────────────────────────────

TOOL_MAP: dict[str, Any] = {
    "scan_planet_production": scan_planet_production,
    "analyze_production_chain": analyze_production_chain,
    "audit_logistics_routes": audit_logistics_routes,
    "check_tech_upgrades": check_tech_upgrades,
    "calculate_power_balance": calculate_power_balance,
    "suggest_station_grouping": suggest_station_grouping,
    "find_idle_factories": find_idle_factories,
    "generate_task_breakdown": generate_task_breakdown,
}


async def execute_tool(
    tool_name: str,
    arguments: str | dict[str, Any],
    ctx: AgentContext,
) -> str:
    """Execute a tool by name and return the result as a JSON string."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}

    tool_fn = TOOL_MAP.get(tool_name)
    if not tool_fn:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        result = await tool_fn(arguments, ctx)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Tool '{tool_name}' failed: {str(e)}"})
