"""OptimizationAgent — 6-Phase ReAct loop for DSP production analysis."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ..llm.base import BaseProvider, Message, ToolDef, ProviderResponse
from ..task_manager.models import TaskItem, TaskPriority, TaskCategory, TaskStatus
from .prompts import SYSTEM_PROMPT, AGENT_USER_PROMPT_TEMPLATE
from .tools import (
    AgentContext,
    TOOL_DEFINITIONS,
    TOOL_MAP,
    execute_tool,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the OptimizationAgent."""

    max_rounds: int = 30
    phase_timeout: float = 30.0  # seconds per LLM call
    total_timeout: float = 300.0  # seconds for entire analysis
    enable_streaming: bool = False


@dataclass
class AnalysisResult:
    """Result of a complete agent analysis run."""

    tasks: list[TaskItem] = field(default_factory=list)
    summary: str = ""
    total_rounds: int = 0
    phases_completed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.tasks) > 0 and len(self.errors) == 0


class OptimizationAgent:
    """DSP production optimization agent using ReAct pattern.

    The agent receives galaxy scan data, reasons through 6 analysis phases,
    calls tools to retrieve detailed information, and produces a structured
    task list of optimization recommendations.
    """

    def __init__(
        self,
        provider: BaseProvider,
        config: AgentConfig | None = None,
    ) -> None:
        self._provider = provider
        self._config = config or AgentConfig()

    async def analyze(
        self,
        scan_data: dict[str, Any],
        progress_callback: Any = None,
    ) -> AnalysisResult:
        """Execute the full 6-Phase analysis pipeline.

        Args:
            scan_data: Galaxy scan result from the DSP plugin.
            progress_callback: Optional async callback(phase, message, pct)
                               for real-time progress updates.

        Returns:
            AnalysisResult with structured TaskItems and summary.
        """
        ctx = AgentContext(scan_data)
        tools: list[ToolDef] = TOOL_DEFINITIONS  # type: ignore[assignment]

        # Build initial messages
        messages: list[Message] = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(
                role="user",
                content=AGENT_USER_PROMPT_TEMPLATE.format(
                    scan_data_json=json.dumps(scan_data, ensure_ascii=False, indent=2)
                ),
            ),
        ]

        result = AnalysisResult()
        phase_progress: dict[str, float] = {}

        try:
            # Main ReAct loop
            for round_idx in range(self._config.max_rounds):
                logger.info(
                    "Agent round %d/%d: %d messages, %d tools",
                    round_idx + 1,
                    self._config.max_rounds,
                    len(messages),
                    len(tools),
                )

                # LLM call with timeout
                try:
                    response = await asyncio.wait_for(
                        self._provider.chat(messages, tools),
                        timeout=self._config.phase_timeout,
                    )
                except asyncio.TimeoutError:
                    result.errors.append(
                        f"LLM call timed out at round {round_idx + 1}"
                    )
                    logger.warning("LLM timeout at round %d", round_idx + 1)
                    break

                # Check stop condition
                if response.finish_reason == "stop" and not response.tool_calls:
                    logger.info("Agent finished: %s", response.content[:200] if response.content else "(no content)")
                    result.summary = response.content or ""
                    break

                # Handle tool calls
                if response.tool_calls:
                    # Add assistant message with tool calls
                    assistant_msg: Message = {
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": response.tool_calls,
                    }
                    messages.append(assistant_msg)

                    # Execute each tool
                    for tc in response.tool_calls:
                        func = tc.get("function", {})
                        tool_name = func.get("name", "")
                        arguments = func.get("arguments", "{}")

                        logger.info(
                            "  Tool: %s(%s)",
                            tool_name,
                            str(arguments)[:100],
                        )

                        tool_result = await execute_tool(
                            tool_name, arguments, ctx
                        )

                        # Add tool result message
                        tool_msg: Message = {
                            "role": "tool",
                            "content": tool_result,
                            "tool_call_id": tc.get("id", ""),
                            "name": tool_name,
                        }
                        messages.append(tool_msg)

                    # Track phase progress
                    phase = _detect_phase(tool_name)
                    phase_progress[phase] = phase_progress.get(phase, 0) + 1
                    if progress_callback:
                        await progress_callback(phase, tool_name, len(phase_progress) / 6.0)

                    continue

                # No tool calls and content present — might be mid-reasoning
                if response.content:
                    # Add as assistant message and let it continue
                    messages.append(Message(
                        role="assistant",
                        content=response.content,
                    ))
                    continue

                # Empty response — stop
                logger.warning("Empty response at round %d", round_idx + 1)
                break

            result.total_rounds = round_idx + 1
            result.phases_completed = list(phase_progress.keys())

            # Extract tasks from the final response
            if result.summary:
                result.tasks = _extract_tasks_from_response(
                    result.summary,
                    scan_data.get("planets", []),
                )

            logger.info(
                "Agent analysis complete: %d rounds, %d tasks, phases: %s",
                result.total_rounds,
                len(result.tasks),
                ", ".join(result.phases_completed) or "none",
            )

        except Exception as e:
            logger.exception("Agent analysis failed")
            result.errors.append(str(e))

        return result


def _detect_phase(tool_name: str) -> str:
    """Map tool name to analysis phase."""
    phase_map = {
        "scan_planet_production": "phase_1_overview",
        "find_idle_factories": "phase_2_bottleneck",
        "audit_logistics_routes": "phase_3_logistics",
        "suggest_station_grouping": "phase_3_logistics",
        "analyze_production_chain": "phase_4_balance",
        "calculate_power_balance": "phase_2_bottleneck",
        "check_tech_upgrades": "phase_5_upgrades",
        "generate_task_breakdown": "phase_6_breakdown",
    }
    return phase_map.get(tool_name, "unknown")


def _extract_tasks_from_response(
    summary: str,
    planets: list[dict[str, Any]],
) -> list[TaskItem]:
    """Try to extract structured tasks from the Agent's final response.

    If the response contains JSON task items, parse them.
    Otherwise, create a single task wrapping the summary.
    """
    tasks: list[TaskItem] = []

    # Try to find JSON task list in the response
    json_start = summary.find("[")
    json_end = summary.rfind("]")

    if json_start != -1 and json_end != -1 and json_end > json_start:
        try:
            raw_tasks = json.loads(summary[json_start : json_end + 1])
            if isinstance(raw_tasks, list):
                for rt in raw_tasks:
                    if isinstance(rt, dict) and "title" in rt:
                        tasks.append(TaskItem(
                            title=rt.get("title", "Untitled"),
                            priority=TaskPriority(
                                rt.get("priority", "medium").lower()
                            ),
                            category=TaskCategory(
                                rt.get("category", "production").lower()
                            ),
                            description=rt.get("description", ""),
                            suggested_action=rt.get("suggested_action", ""),
                            planet=rt.get("planet"),
                            estimated_effort=rt.get("estimated_effort", "未估"),
                        ))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse task JSON from summary: %s", e)

    # Fallback: wrap the entire summary as one task
    if not tasks and summary.strip():
        tasks.append(TaskItem(
            title="AI 分析结果",
            priority=TaskPriority.HIGH,
            category=TaskCategory.PRODUCTION,
            description=summary.strip(),
            suggested_action="查看详细分析",
        ))

    return tasks
