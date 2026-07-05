"""Integration tests for WebSocket protocol — message encode/decode round-trip."""

import asyncio
import json

import pytest
import websockets
from websockets.asyncio.server import serve

from dsp_ai_advisor.models import MessageEnvelope, SnapshotData, ItemStat, SnapshotSummary


# ── 测试数据工厂 ──────────────────────────────────────────

def make_sample_snapshot() -> SnapshotData:
    """Create a SnapshotData matching the C# plugin output format."""
    return SnapshotData(
        snapshot_id="a1b2c3d4",
        game_tick=72000,
        elapsed_seconds=5.0,
        timestamp_unix=1712345678,
        production={
            "1001": ItemStat(
                item_id=1001,
                item_name="铁矿",
                produced=1200,
                consumed=1100,
                net=100,
                rate_per_min=240.0,
            ),
            "1101": ItemStat(
                item_id=1101,
                item_name="铁块",
                produced=800,
                consumed=950,
                net=-150,
                rate_per_min=160.0,
            ),
        },
        summary=SnapshotSummary(
            total_items_tracked=2,
            items_in_deficit=1,
            items_in_surplus=1,
        ),
    )


def make_envelope(snapshot: SnapshotData) -> dict:
    """Encode a snapshot as a protocol envelope (matching C# MessageCodec.EncodeSnapshot)."""
    return {
        "channel": "snapshot",
        "type": "periodic_snapshot",
        "payload": json.loads(snapshot.model_dump_json()),
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": 1712345678,
    }


# ── 消息模型测试 ──────────────────────────────────────────

class TestMessageModels:
    """Verify pydantic models parse correctly."""

    def test_snapshotdata_from_json(self):
        """SnapshotData should parse from a protocol envelope's payload."""
        snap = make_sample_snapshot()
        envelope = make_envelope(snap)

        parsed = SnapshotData(**envelope["payload"])
        assert parsed.snapshot_id == "a1b2c3d4"
        assert parsed.game_tick == 72000
        assert len(parsed.production) == 2
        assert parsed.summary.items_in_deficit == 1
        assert parsed.production["1101"].item_name == "铁块"
        assert parsed.production["1101"].net == -150

    def test_message_envelope_parsing(self):
        """MessageEnvelope should parse a full protocol message."""
        snap = make_sample_snapshot()
        raw = json.dumps(make_envelope(snap))

        parsed = MessageEnvelope(**json.loads(raw))
        assert parsed.channel == "snapshot"
        assert parsed.type == "periodic_snapshot"
        assert parsed.payload is not None

    def test_empty_snapshot(self):
        """Snapshot with no production data should still parse."""
        snap = SnapshotData(
            snapshot_id="empty",
            game_tick=0,
            elapsed_seconds=0.0,
            timestamp_unix=0,
        )
        assert snap.production == {}
        assert snap.summary is None


# ── WebSocket 集成测试 ────────────────────────────────────

class TestWsRoundTrip:
    """End-to-end: server sends envelope → client receives and parses."""

    @pytest.mark.asyncio
    async def test_send_receive_snapshot(self, unused_tcp_port: int):
        """Client connects, server sends a snapshot envelope, client parses it."""
        snap = make_sample_snapshot()
        envelope = make_envelope(snap)

        async def _handler(ws):
            await ws.send(json.dumps(envelope))
            await ws.close()

        async with serve(_handler, "localhost", unused_tcp_port):
            async with websockets.connect(
                f"ws://localhost:{unused_tcp_port}"
            ) as ws:
                raw = await ws.recv()
                data = json.loads(raw)
                msg = MessageEnvelope(**data)
                assert msg.channel == "snapshot"

                parsed = SnapshotData(**msg.payload)
                assert parsed.snapshot_id == "a1b2c3d4"
                assert parsed.production["1001"].item_name == "铁矿"
                assert parsed.production["1101"].net == -150

    @pytest.mark.asyncio
    async def test_multiple_messages(self, unused_tcp_port: int):
        """Client receives multiple snapshot messages in sequence."""
        snap1 = make_sample_snapshot()
        snap2 = make_sample_snapshot()
        snap2.snapshot_id = "x9y8z7w6"

        messages = [json.dumps(make_envelope(snap1)), json.dumps(make_envelope(snap2))]

        async def _handler(ws):
            for msg in messages:
                await ws.send(msg)
            await ws.close()

        received = []
        async with serve(_handler, "localhost", unused_tcp_port):
            async with websockets.connect(
                f"ws://localhost:{unused_tcp_port}"
            ) as ws:
                async for raw in ws:
                    data = json.loads(raw)
                    msg = MessageEnvelope(**data)
                    snap = SnapshotData(**msg.payload)
                    received.append(snap)

        assert len(received) == 2
        assert received[0].snapshot_id == "a1b2c3d4"
        assert received[1].snapshot_id == "x9y8z7w6"


# ── 序列化一致性测试 ───────────────────────────────────────

class TestSerializationConsistency:
    """Ensure Python and C# produce compatible JSON."""

    def test_snapshot_json_format_matches_csharp(self):
        """Python SnapshotData JSON should match the C# JsonProperty names."""
        snap = make_sample_snapshot()
        raw = snap.model_dump_json()

        data = json.loads(raw)
        # C# uses snake_case via JsonProperty attributes
        assert "snapshot_id" in data
        assert "game_tick" in data
        assert "elapsed_seconds" in data
        assert "timestamp_unix" in data
        assert "production" in data
        assert "summary" in data
        # ItemStat fields
        stat = data["production"]["1001"]
        assert "item_id" in stat
        assert "item_name" in stat
        assert "produced" in stat
        assert "consumed" in stat
        assert "net" in stat
        assert "rate_per_min" in stat

    def test_envelope_format_matches_csharp(self):
        """Envelope JSON should match C# MessageCodec output."""
        snap = make_sample_snapshot()
        envelope = make_envelope(snap)
        raw = json.dumps(envelope)

        data = json.loads(raw)
        assert "channel" in data
        assert "type" in data
        assert "payload" in data
        assert "id" in data
        assert "timestamp" in data
