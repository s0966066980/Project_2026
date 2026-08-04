"""語音助理路由。"""

import asyncio
import json
import os
import tempfile
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from modules.voice_turn import VoiceTurnError
from modules.voice_turn import runtime as voice_turn_runtime

from services.commercial_context_service import scope_from_device_principal
from utils.auth_utils import check_rate_limit, read_limited_upload, require_kiosk_token
from utils.file_utils import write_binary_file


async def _stream_durable_turn_events(
    *,
    module,
    scope,
    voice_turn_id: str,
    run_task: asyncio.Task,
    after_sequence: int,
    poll_interval: float = 0.03,
):
    """Replay new durable events while inference and playback are still running."""
    last_sequence = max(0, int(after_sequence))
    while True:
        events = await asyncio.to_thread(
            module.replay,
            scope=scope,
            voice_turn_id=voice_turn_id,
            after_sequence=last_sequence,
        )
        for event in events:
            last_sequence = max(last_sequence, int(event.get("sequence") or 0))
            yield (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            if event.get("terminal"):
                return

        if run_task.done():
            try:
                await asyncio.shield(run_task)
            except asyncio.CancelledError:
                raise
            except Exception:
                yield b'{"error":"voice_turn_execution_failed"}\n'
                return
            # The terminal commit may have raced with the replay above. Loop
            # immediately once more so that the durable terminal event wins.
            final_events = await asyncio.to_thread(
                module.replay,
                scope=scope,
                voice_turn_id=voice_turn_id,
                after_sequence=last_sequence,
            )
            if not final_events:
                return
            for event in final_events:
                last_sequence = max(last_sequence, int(event.get("sequence") or 0))
                yield (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
                if event.get("terminal"):
                    return
            return

        await asyncio.sleep(poll_interval)


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["voice"])
    running_turns: dict[tuple[str, str, str], asyncio.Task] = {}

    @router.post("/ask/stream")
    async def process_voice_stream(
        request: Request,
        session_id: str = Form(...),
        media: UploadFile = File(...),
        voice_turn_id: str = Form(default=""),
        after_sequence: int = Form(default=0),
    ):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        check_rate_limit(request, "voice_stream", limit=30, key=session_id)
        turn_id = str(voice_turn_id or uuid4())
        media_bytes = await read_limited_upload(media)
        suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name
        await asyncio.to_thread(write_binary_file, temp_path, media_bytes)

        module = voice_turn_runtime.default_module()
        try:
            await asyncio.to_thread(
                module.accept,
                scope=scope,
                session_id=session_id,
                audio_ref=temp_path,
                voice_turn_id=turn_id,
            )
        except VoiceTurnError as exc:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise HTTPException(status_code=409, detail={"code": exc.code}) from exc

        async def _run_to_terminal():
            result = None
            for attempt in range(3):
                result = await asyncio.to_thread(
                    module.run,
                    scope=scope,
                    voice_turn_id=turn_id,
                    retry_budget_exhausted=attempt == 2,
                )
                if not result.get("retryable"):
                    break
                await asyncio.sleep(0.1 * (2**attempt))
            return result

        run_task = asyncio.create_task(_run_to_terminal())
        run_key = (str(scope.tenant_id), str(scope.store_id), turn_id)
        running_turns[run_key] = run_task

        def _delete_input(_task):
            if running_turns.get(run_key) is _task:
                running_turns.pop(run_key, None)
            if os.path.exists(temp_path):
                os.remove(temp_path)

        run_task.add_done_callback(_delete_input)

        async def _stream_with_cleanup():
            try:
                # Client disconnect cancels only this subscription. The accepted
                # durable task remains owned by running_turns until its callback.
                async for event in _stream_durable_turn_events(
                    module=module,
                    scope=scope,
                    voice_turn_id=turn_id,
                    run_task=run_task,
                    after_sequence=after_sequence,
                ):
                    yield event
            except asyncio.CancelledError:
                return

        return StreamingResponse(
            _stream_with_cleanup(),
            media_type="application/x-ndjson",
        )

    @router.get("/ask/stream/{voice_turn_id}")
    async def replay_voice_stream(request: Request, voice_turn_id: str, after_sequence: int = 0):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        module = voice_turn_runtime.default_module()
        run_key = (str(scope.tenant_id), str(scope.store_id), voice_turn_id)

        async def _replay():
            try:
                active = running_turns.get(run_key)
                if active is not None:
                    await asyncio.shield(active)
                else:
                    await asyncio.to_thread(
                        module.run,
                        scope=scope,
                        voice_turn_id=voice_turn_id,
                        retry_budget_exhausted=True,
                    )
                events = await asyncio.to_thread(
                    module.replay, scope=scope, voice_turn_id=voice_turn_id, after_sequence=after_sequence
                )
            except VoiceTurnError as exc:
                yield (json.dumps({"error": exc.code}) + "\n").encode()
                return
            for event in events:
                yield (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode()

        return StreamingResponse(_replay(), media_type="application/x-ndjson")

    return router
