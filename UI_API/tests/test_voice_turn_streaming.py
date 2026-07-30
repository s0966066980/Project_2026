import asyncio
import json

from routes.voice_routes import _stream_durable_turn_events


def test_assistant_result_streams_before_tts_terminal_event():
    events = []

    class Module:
        def replay(self, *, scope, voice_turn_id, after_sequence):
            return [event for event in events if event["sequence"] > after_sequence]

    async def scenario():
        async def produce():
            events.append({"sequence": 1, "type": "accepted", "terminal": False})
            await asyncio.sleep(0.01)
            events.append({"sequence": 2, "type": "assistant_result", "terminal": False})
            await asyncio.sleep(0.08)
            events.append({"sequence": 3, "type": "completed", "terminal": True})

        run_task = asyncio.create_task(produce())
        observed = []
        async for raw in _stream_durable_turn_events(
            module=Module(),
            scope=None,
            voice_turn_id="turn-1",
            run_task=run_task,
            after_sequence=0,
            poll_interval=0.005,
        ):
            event = json.loads(raw)
            observed.append(event["type"])
            if event["type"] == "assistant_result":
                assert run_task.done() is False
        return observed

    assert asyncio.run(scenario()) == ["accepted", "assistant_result", "completed"]
