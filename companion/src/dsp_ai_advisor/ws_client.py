"""Async WebSocket client — connects to the C# plugin's WsServer on port 8470."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Awaitable

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
        if self._connection is None:
            return False
        try:
            return self._connection.state.name == "OPEN"
        except Exception:
            return False

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
