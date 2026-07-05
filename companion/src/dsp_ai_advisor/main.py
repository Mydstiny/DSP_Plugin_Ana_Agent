"""DSP AI Advisor Companion App — Entry Point."""

import asyncio
import logging
import signal
import sys

logger = logging.getLogger(__name__)


async def main_async() -> None:
    """Main async entry point."""
    logger.info("DSP AI Advisor Companion v%s starting...", __import__("dsp_ai_advisor").__version__)

    # TODO Phase 1: WebSocket client connect
    # TODO Phase 2: Rule engine + LLM pipeline + Agent init
    # TODO Phase 4: System tray GUI

    # Keep running until interrupted
    stop = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutting down...")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop.wait()


def main() -> None:
    """Console script entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
