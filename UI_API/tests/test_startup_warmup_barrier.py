import asyncio
import threading


def test_parallel_app_startup_waits_for_shared_warmup(monkeypatch):
    from backend.bootstrap import startup

    warmup_started = asyncio.Event()
    release_warmup = asyncio.Event()
    warmup_calls = 0

    async def fake_background_init_once():
        nonlocal warmup_calls
        warmup_calls += 1
        warmup_started.set()
        await release_warmup.wait()

    monkeypatch.setattr(startup, "_background_init_done", False)
    monkeypatch.setattr(startup, "_background_init_claim_lock", threading.Lock())
    monkeypatch.setattr(startup, "_background_init_ready", threading.Event())
    monkeypatch.setattr(startup, "_background_init_once", fake_background_init_once)

    async def exercise_barrier():
        first_server = asyncio.create_task(startup.background_init())
        await warmup_started.wait()
        second_server = asyncio.create_task(startup.background_init())
        await asyncio.sleep(0.05)

        assert not first_server.done()
        assert not second_server.done()
        assert warmup_calls == 1

        release_warmup.set()
        await asyncio.gather(first_server, second_server)

    asyncio.run(exercise_barrier())
    assert warmup_calls == 1
