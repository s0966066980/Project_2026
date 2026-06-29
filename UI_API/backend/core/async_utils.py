import asyncio


class LoopBoundSemaphore:
    """Lazily create an asyncio.Semaphore for the current running event loop."""

    def __init__(self, value: int = 1):
        self.value = value
        self._loop = None
        self._semaphore = None

    def _current(self):
        loop = asyncio.get_running_loop()
        if self._loop is not loop or self._semaphore is None:
            self._loop = loop
            self._semaphore = asyncio.Semaphore(self.value)
        return self._semaphore

    def locked(self) -> bool:
        try:
            return self._current().locked()
        except RuntimeError:
            return False

    async def __aenter__(self):
        await self._current().acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._current().release()

