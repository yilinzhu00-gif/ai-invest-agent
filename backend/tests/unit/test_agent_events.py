from uuid import uuid4

import pytest

from backend.app.agent.events import AgentEventEmitter, AgentEventType


@pytest.mark.asyncio
async def test_emitter_produces_safe_typed_event_payload() -> None:
    received = []

    async def sink(event: object) -> None:
        received.append(event)

    run_id = uuid4()
    emitted = await AgentEventEmitter(sink).emit(
        AgentEventType.PLANNING_START,
        "Planner Agent started",
        run_id=run_id,
        metadata={"workflow": "research"},
    )

    assert emitted.event_type is AgentEventType.PLANNING_START
    assert emitted.run_id == run_id
    assert emitted.as_payload()["type"] == "PLANNING_START"
    assert received == [emitted]
