"""Pydantic data models matching the WebSocket protocol and C# SnapshotData."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ItemStat(BaseModel):
    """Single item production stat within a snapshot."""
    item_id: int
    item_name: str
    produced: int
    consumed: int
    net: int
    rate_per_min: float


class SnapshotSummary(BaseModel):
    """Aggregate summary of a snapshot."""
    total_items_tracked: int
    items_in_deficit: int
    items_in_surplus: int


class SnapshotData(BaseModel):
    """Periodic production snapshot payload."""
    snapshot_id: str
    game_tick: int
    elapsed_seconds: float
    timestamp_unix: int
    production: dict[str, ItemStat] = Field(default_factory=dict)
    summary: SnapshotSummary | None = None


class MessageEnvelope(BaseModel):
    """Top-level WebSocket message envelope."""
    channel: str
    type: str
    payload: dict | None = None
    id: str
    timestamp: int
