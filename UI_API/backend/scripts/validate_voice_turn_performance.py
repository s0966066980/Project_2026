#!/usr/bin/env python3
"""Measure the real durable Voice Turn pipeline without retaining media or text."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
UI_API_DIR = BACKEND_DIR.parent
for import_root in (UI_API_DIR, BACKEND_DIR):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from services.tts_service import get_tts  # noqa: E402

UTTERANCES = {
    "conversation": "請問今天有什麼會員優惠？",
    "ordering": "我要一份薯條和一杯可樂。",
}


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 2)


async def _sample_audio() -> dict[str, bytes]:
    provider = get_tts()
    return {category: await provider.synthesize(text) for category, text in UTTERANCES.items()}


async def _run(args: argparse.Namespace) -> dict:
    credential = json.loads(args.credential_file.read_text(encoding="utf-8"))
    audio = await _sample_audio()
    session_id = f"voice-performance-{uuid4()}"
    samples = []

    timeout = httpx.Timeout(args.timeout_seconds)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout) as client:
        response = await client.post(
            "/api/device/auth/session",
            json={"key_id": credential["key_id"], "credential": credential["credential"]},
        )
        response.raise_for_status()

        categories = ["conversation", "ordering"]
        for sample_index in range(args.samples_per_category * len(categories)):
            category = categories[sample_index % len(categories)]
            turn_id = str(uuid4())
            started = time.perf_counter()
            response_wait_ms = None
            terminal_events = []
            event_types = []
            sequences = []
            playback_status = ""
            async with client.stream(
                "POST",
                "/api/ask/stream",
                data={
                    "session_id": session_id,
                    "voice_turn_id": turn_id,
                    "after_sequence": "0",
                },
                files={"media": (f"{category}.mp3", audio[category], "audio/mpeg")},
            ) as stream:
                stream.raise_for_status()
                async for line in stream.aiter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise RuntimeError(str(event["error"]))
                    if event.get("voice_turn_id") != turn_id:
                        raise RuntimeError("voice_turn_identity_mismatch")
                    event_type = str(event.get("type") or "")
                    event_types.append(event_type)
                    sequences.append(int(event.get("sequence") or 0))
                    if event_type == "assistant_result" and response_wait_ms is None:
                        response_wait_ms = round((time.perf_counter() - started) * 1000, 2)
                    if event.get("terminal"):
                        terminal_events.append(event_type)
                        playback_status = str((event.get("payload") or {}).get("playback_status") or "")

            if response_wait_ms is None:
                raise RuntimeError("assistant_result_missing")
            if len(terminal_events) != 1:
                raise RuntimeError("terminal_event_count_invalid")
            if sequences != sorted(set(sequences)):
                raise RuntimeError("event_sequence_not_monotonic")
            samples.append(
                {
                    "sample": sample_index + 1,
                    "category": category,
                    "response_wait_ms": response_wait_ms,
                    "terminal_type": terminal_events[0],
                    "playback_status": playback_status,
                    "event_types": event_types,
                }
            )

    waits = [float(sample["response_wait_ms"]) for sample in samples]
    p95 = _percentile(waits, 0.95)
    expected_events = ["accepted", "transcribing", "transcript", "assistant_result", "completed"]
    event_protocol_valid = all(
        sample["terminal_type"] == "completed"
        and sample["event_types"] == expected_events
        and sample["playback_status"] in {"available", "degraded"}
        for sample in samples
    )
    return {
        "status": "passed" if p95 <= args.max_p95_ms and event_protocol_valid else "failed",
        "sample_count": len(samples),
        "categories": {category: sum(sample["category"] == category for sample in samples) for category in UTTERANCES},
        "response_wait_ms": {
            "minimum": round(min(waits), 2),
            "median": _percentile(waits, 0.50),
            "p95": p95,
            "maximum": round(max(waits), 2),
            "required_p95_maximum": args.max_p95_ms,
        },
        "event_protocol_valid": event_protocol_valid,
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:9000")
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--samples-per-category", type=int, default=15)
    parser.add_argument("--max-p95-ms", type=float, default=3000.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args()
    if args.samples_per_category < 1:
        parser.error("--samples-per-category must be positive")

    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
