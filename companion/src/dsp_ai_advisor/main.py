"""DSP AI Advisor Companion App — Entry Point."""

import asyncio
import logging
import signal
import sys

from .ws_client import DspWsClient
from .models import SnapshotData

logger = logging.getLogger(__name__)


async def _on_snapshot(snapshot: SnapshotData) -> None:
    """Example callback — log deficit items in detail."""
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
