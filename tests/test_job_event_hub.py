from __future__ import annotations

import asyncio
import json

from backend.core.server_helpers import JobEventHub


def _payload(chunk: str) -> dict:
    line = next(line for line in chunk.splitlines() if line.startswith("data: "))
    return json.loads(line[6:])


def test_job_event_hub_replays_cached_terminal_event() -> None:
    async def run() -> None:
        hub = JobEventHub()
        await hub.publish("task-1", {"stage": "audio", "progress": 5})
        await hub.publish("task-1", {"stage": "done", "progress": 100, "result": {"ok": True}})

        events = []
        async for chunk in hub.subscribe("task-1"):
            events.append(_payload(chunk))

        assert [event["stage"] for event in events] == ["audio", "done"]
        assert events[-1]["result"] == {"ok": True}

    asyncio.run(run())


def test_job_event_hub_cancel_stops_background_task() -> None:
    async def run() -> None:
        hub = JobEventHub()
        cancelled = asyncio.Event()

        async def runner() -> None:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        await hub.start("task-2", runner)
        await asyncio.sleep(0)
        assert await hub.cancel("task-2") is True
        await asyncio.wait_for(cancelled.wait(), timeout=1)

    asyncio.run(run())
