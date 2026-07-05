"""DSP AI Advisor Companion App — Entry Point."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

from .ws_client import DspWsClient
from .models import SnapshotData, MessageEnvelope
from .llm.config import LLMSettings
from .agent.agent import OptimizationAgent, AgentConfig
from .task_manager.manager import TaskManager

logger = logging.getLogger(__name__)

# Global references for WebSocket callbacks
_agent: OptimizationAgent | None = None
_task_manager: TaskManager | None = None
_ws_client: DspWsClient | None = None


async def _on_snapshot(snapshot: SnapshotData) -> None:
    """Handle periodic production snapshot."""
    if snapshot.summary and snapshot.summary.items_in_deficit > 0:
        deficit_items = [
            (item_id, stat)
            for item_id, stat in snapshot.production.items()
            if stat.net < 0
        ]
        for item_id, stat in deficit_items[:5]:
            logger.info(
                "  DEFICIT %s (#%s): net=%d, rate=%.1f/min",
                stat.item_name, item_id, stat.net, stat.rate_per_min,
            )


async def _on_galaxy_scan_result(payload: dict) -> None:
    """Handle a galaxy scan result from the DSP plugin."""
    global _agent, _task_manager, _ws_client

    if _agent is None or _task_manager is None:
        logger.warning("Agent or TaskManager not initialized — ignoring scan result")
        return

    logger.info("Galaxy scan received, starting agent analysis...")
    logger.info(
        "  Planets: %d, Stations: %d, Routes: %d",
        len(payload.get("planets", [])),
        len(payload.get("stations", [])),
        len(payload.get("routes", [])),
    )

    # Run agent analysis
    async def _progress(phase: str, tool: str, pct: float) -> None:
        logger.info("  [%.0f%%] Phase %s: %s", pct * 100, phase, tool)

    try:
        result = await _agent.analyze(payload, progress_callback=_progress)

        if result.errors:
            for err in result.errors:
                logger.error("Agent error: %s", err)

        if result.tasks:
            added = _task_manager.merge_and_dedup(result.tasks)
            logger.info(
                "Analysis complete: %d new tasks added, %d active total",
                len(added),
                _task_manager.active_count,
            )

            # Print task list
            active = _task_manager.get_active_tasks(limit=20)
            for i, task in enumerate(active, 1):
                logger.info(
                    "  %d. [%s] %s — %s",
                    i,
                    task.priority.value.upper(),
                    task.title,
                    task.planet or "全局",
                )
        else:
            logger.warning("Agent produced no tasks. Raw summary: %.200s", result.summary)

    except Exception:
        logger.exception("Agent analysis failed")


async def _dispatch_message(envelope: MessageEnvelope) -> None:
    """Dispatch WebSocket messages to handlers."""
    if (
        envelope.channel == "snapshot"
        and envelope.type == "galaxy_scan_result"
        and envelope.payload
    ):
        await _on_galaxy_scan_result(envelope.payload)

    elif envelope.channel == "snapshot" and envelope.type == "periodic_snapshot":
        if envelope.payload:
            snapshot = SnapshotData(**envelope.payload)
            await _on_snapshot(snapshot)


def _load_config(config_path: str | None = None) -> LLMSettings:
    """Load LLM configuration from config.yaml."""
    if config_path:
        path = Path(config_path)
    else:
        path = Path("config.yaml")

    if not path.exists():
        logger.warning(
            "config.yaml not found at %s. Copy config.yaml.example and edit it.",
            path.absolute(),
        )
        # Return empty config — will fail on provider creation
        return LLMSettings(default="claude", providers={})

    logger.info("Loading config from %s", path.absolute())
    return LLMSettings.from_yaml(str(path))


async def main_async(config_path: str | None = None) -> None:
    """Main async entry point."""
    global _agent, _task_manager, _ws_client

    version = __import__("dsp_ai_advisor").__version__
    logger.info("DSP AI Advisor Companion v%s starting...", version)

    # Load config
    config = _load_config(config_path)
    if not config.providers:
        logger.error("No LLM providers configured. Exiting.")
        return

    provider = config.create_provider()
    logger.info("LLM provider: %s (model=%s)", config.default, config.providers[config.default].model)

    # Initialize components
    _agent = OptimizationAgent(provider, AgentConfig())
    _task_manager = TaskManager()

    # Connect to DSP plugin
    _ws_client = DspWsClient(host="localhost", port=8470)
    # Register the dispatch function to handle all message types
    _ws_client._dispatch = _dispatch_message  # type: ignore[assignment]

    await _ws_client.connect()

    # Keep running until interrupted
    stop = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutting down...")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    logger.info("Ready. Waiting for DSP game to connect...")
    await stop.wait()

    await _ws_client.disconnect()
    logger.info("Goodbye.")


def main() -> None:
    """Console script entry point."""
    parser = argparse.ArgumentParser(description="DSP AI Advisor Companion")
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Path to config.yaml (default: ./config.yaml)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(main_async(config_path=args.config))


if __name__ == "__main__":
    main()
