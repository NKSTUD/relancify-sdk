from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from agents.result import RunResultStreaming


class SyncAgentStream:
    """Synchronous iterator over native Agents SDK stream events."""

    def __init__(self, factory: Callable[[], RunResultStreaming]) -> None:
        self._factory = factory
        self._loop: asyncio.AbstractEventLoop | None = None
        self._result: RunResultStreaming | None = None
        self._events: Any = None

    @property
    def result(self) -> RunResultStreaming | None:
        return self._result

    @property
    def final_output(self) -> Any:
        return self._result.final_output if self._result is not None else None

    def __iter__(self) -> "SyncAgentStream":
        return self

    def __next__(self) -> Any:
        self._ensure_started()
        assert self._loop is not None
        assert self._events is not None
        try:
            return self._loop.run_until_complete(self._events.__anext__())
        except StopAsyncIteration:
            self.close()
            raise StopIteration from None

    def close(self) -> None:
        if self._loop is None:
            return
        if self._result is not None and not self._result.is_complete:
            self._result.cancel()
            self._loop.run_until_complete(asyncio.sleep(0))
        self._loop.close()
        self._loop = None

    def __enter__(self) -> "SyncAgentStream":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def _ensure_started(self) -> None:
        if self._loop is not None:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "Synchronous streaming cannot run inside an active event loop; "
                "use AsyncRelancifyClient instead."
            )

        self._loop = asyncio.new_event_loop()

        async def start() -> RunResultStreaming:
            return self._factory()

        self._result = self._loop.run_until_complete(start())
        self._events = self._result.stream_events().__aiter__()


class AsyncAgentStream:
    """Asynchronous iterator over native Agents SDK stream events."""

    def __init__(
        self,
        factory: Callable[[], Awaitable[RunResultStreaming]],
    ) -> None:
        self._factory = factory
        self._result: RunResultStreaming | None = None
        self._events: Any = None

    @property
    def result(self) -> RunResultStreaming | None:
        return self._result

    @property
    def final_output(self) -> Any:
        return self._result.final_output if self._result is not None else None

    def __aiter__(self) -> "AsyncAgentStream":
        return self

    async def __anext__(self) -> Any:
        await self._ensure_started()
        assert self._events is not None
        return await self._events.__anext__()

    async def aclose(self) -> None:
        if self._result is not None and not self._result.is_complete:
            self._result.cancel()
            await asyncio.sleep(0)

    async def __aenter__(self) -> "AsyncAgentStream":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        await self.aclose()

    async def _ensure_started(self) -> None:
        if self._result is not None:
            return
        self._result = await self._factory()
        self._events = self._result.stream_events().__aiter__()
