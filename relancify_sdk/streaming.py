from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any

from agents.result import RunResultStreaming

from relancify_sdk.results import AgentRunResult, AgentStreamEvent

_OUTPUT_DELTA_TYPES = {
    "response.audio.delta",
    "response.audio_transcript.delta",
    "response.output_text.delta",
    "response.refusal.delta",
}


class SyncAgentStream:
    """Synchronous normalized stream for hosted or local execution."""

    def __init__(
        self,
        *,
        local_factory: Callable[[], RunResultStreaming] | None = None,
        hosted_events: Iterator[dict[str, Any]] | None = None,
    ) -> None:
        if (local_factory is None) == (hosted_events is None):
            raise ValueError("Provide exactly one stream source")
        self._local_factory = local_factory
        self._hosted_events = hosted_events
        self._loop: asyncio.AbstractEventLoop | None = None
        self._native_result: RunResultStreaming | None = None
        self._native_events: Any = None
        self._pending: deque[AgentStreamEvent] = deque()
        self._completed = False
        self._closed = False
        self._result: AgentRunResult | None = None

    @classmethod
    def local(cls, factory: Callable[[], RunResultStreaming]) -> "SyncAgentStream":
        return cls(local_factory=factory)

    @classmethod
    def hosted(cls, events: Iterator[dict[str, Any]]) -> "SyncAgentStream":
        return cls(hosted_events=events)

    @property
    def result(self) -> AgentRunResult | None:
        return self._result

    @property
    def final_output(self) -> Any:
        return self._result.output if self._result is not None else None

    def __iter__(self) -> "SyncAgentStream":
        return self

    def __next__(self) -> AgentStreamEvent:
        if self._pending:
            return self._pending.popleft()
        if self._completed:
            raise StopIteration
        if self._hosted_events is not None:
            return self._next_hosted()
        return self._next_local()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._completed = True
        if self._loop is not None:
            if self._native_result is not None and not self._native_result.is_complete:
                self._native_result.cancel()
                self._loop.run_until_complete(asyncio.sleep(0))
            self._loop.close()
            self._loop = None
        close = getattr(self._hosted_events, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> "SyncAgentStream":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def _next_hosted(self) -> AgentStreamEvent:
        if self._hosted_events is None:
            raise RuntimeError("Hosted stream failed to initialize")
        try:
            raw = next(self._hosted_events)
        except StopIteration:
            self.close()
            raise
        except BaseException:
            self.close()
            raise

        event = _normalize_hosted_event(raw)
        if event.type == "run.completed":
            self._result = AgentRunResult.from_hosted(event.data)
        return event

    def _next_local(self) -> AgentStreamEvent:
        self._ensure_local_started()
        if self._pending:
            return self._pending.popleft()
        if self._loop is None or self._native_events is None:
            raise RuntimeError("Synchronous stream failed to initialize")

        while True:
            try:
                raw = self._loop.run_until_complete(self._native_events.__anext__())
            except StopAsyncIteration:
                return self._complete_local()
            except BaseException:
                self.close()
                raise
            event = _normalize_local_event(raw)
            if event is not None:
                return event

    def _ensure_local_started(self) -> None:
        if self._loop is not None:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "Synchronous streaming cannot run inside an active event loop; "
                "use AsyncRelancify instead."
            )

        self._loop = asyncio.new_event_loop()
        if self._local_factory is None:
            raise RuntimeError("Local stream factory is missing")
        self._native_result = self._loop.run_until_complete(
            _start_sync_factory(self._local_factory)
        )
        self._native_events = self._native_result.stream_events().__aiter__()
        self._pending.append(
            AgentStreamEvent(
                type="run.started",
                data={"execution": "local"},
                raw=self._native_result,
            )
        )

    def _complete_local(self) -> AgentStreamEvent:
        if self._native_result is None:
            raise RuntimeError("Local stream result is missing")
        self._result = AgentRunResult.from_local(self._native_result)
        self._completed = True
        event = AgentStreamEvent(
            type="run.completed",
            data=self._result.to_event_data(),
            raw=self._native_result,
        )
        self.close()
        return event


class AsyncAgentStream:
    """Asynchronous normalized stream for hosted or local execution."""

    def __init__(
        self,
        *,
        local_factory: Callable[[], Awaitable[RunResultStreaming]] | None = None,
        hosted_events: AsyncIterator[dict[str, Any]] | None = None,
    ) -> None:
        if (local_factory is None) == (hosted_events is None):
            raise ValueError("Provide exactly one stream source")
        self._local_factory = local_factory
        self._hosted_events = hosted_events
        self._native_result: RunResultStreaming | None = None
        self._native_events: Any = None
        self._pending: deque[AgentStreamEvent] = deque()
        self._completed = False
        self._closed = False
        self._result: AgentRunResult | None = None

    @classmethod
    def local(
        cls,
        factory: Callable[[], Awaitable[RunResultStreaming]],
    ) -> "AsyncAgentStream":
        return cls(local_factory=factory)

    @classmethod
    def hosted(
        cls,
        events: AsyncIterator[dict[str, Any]],
    ) -> "AsyncAgentStream":
        return cls(hosted_events=events)

    @property
    def result(self) -> AgentRunResult | None:
        return self._result

    @property
    def final_output(self) -> Any:
        return self._result.output if self._result is not None else None

    def __aiter__(self) -> "AsyncAgentStream":
        return self

    async def __anext__(self) -> AgentStreamEvent:
        if self._pending:
            return self._pending.popleft()
        if self._completed:
            raise StopAsyncIteration
        if self._hosted_events is not None:
            return await self._next_hosted()
        return await self._next_local()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._completed = True
        if self._native_result is not None and not self._native_result.is_complete:
            self._native_result.cancel()
            await asyncio.sleep(0)
        close = getattr(self._hosted_events, "aclose", None)
        if callable(close):
            await close()

    async def __aenter__(self) -> "AsyncAgentStream":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        await self.aclose()

    async def _next_hosted(self) -> AgentStreamEvent:
        if self._hosted_events is None:
            raise RuntimeError("Hosted stream failed to initialize")
        try:
            raw = await self._hosted_events.__anext__()
        except StopAsyncIteration:
            self._completed = True
            raise
        except BaseException:
            await self.aclose()
            raise
        event = _normalize_hosted_event(raw)
        if event.type == "run.completed":
            self._result = AgentRunResult.from_hosted(event.data)
        return event

    async def _next_local(self) -> AgentStreamEvent:
        await self._ensure_local_started()
        if self._pending:
            return self._pending.popleft()
        if self._native_events is None:
            raise RuntimeError("Asynchronous stream failed to initialize")

        while True:
            try:
                raw = await self._native_events.__anext__()
            except StopAsyncIteration:
                return self._complete_local()
            except BaseException:
                await self.aclose()
                raise
            event = _normalize_local_event(raw)
            if event is not None:
                return event

    async def _ensure_local_started(self) -> None:
        if self._native_result is not None:
            return
        if self._local_factory is None:
            raise RuntimeError("Local stream factory is missing")
        self._native_result = await self._local_factory()
        self._native_events = self._native_result.stream_events().__aiter__()
        self._pending.append(
            AgentStreamEvent(
                type="run.started",
                data={"execution": "local"},
                raw=self._native_result,
            )
        )

    def _complete_local(self) -> AgentStreamEvent:
        if self._native_result is None:
            raise RuntimeError("Local stream result is missing")
        self._result = AgentRunResult.from_local(self._native_result)
        self._completed = True
        return AgentStreamEvent(
            type="run.completed",
            data=self._result.to_event_data(),
            raw=self._native_result,
        )


async def _start_sync_factory(
    factory: Callable[[], RunResultStreaming],
) -> RunResultStreaming:
    return factory()


def _normalize_hosted_event(raw: dict[str, Any]) -> AgentStreamEvent:
    event_type = str(raw.get("event") or raw.get("type") or "message")
    data = raw.get("data")
    delta = data.get("delta") if isinstance(data, dict) else None
    return AgentStreamEvent(type=event_type, data=data, delta=delta, raw=raw)


def _normalize_local_event(raw: Any) -> AgentStreamEvent | None:
    native_type = str(getattr(raw, "type", ""))
    if native_type == "raw_response_event":
        data = getattr(raw, "data", None)
        response_type = str(getattr(data, "type", ""))
        if response_type in {"response.created", "response.completed"}:
            return None
        if response_type in _OUTPUT_DELTA_TYPES:
            delta = getattr(data, "delta", None)
            return AgentStreamEvent(
                type="output.delta",
                data={"delta": delta, "native_type": response_type},
                delta=delta,
                raw=raw,
            )
        if response_type.endswith(".delta"):
            return AgentStreamEvent(
                type="run.event",
                data={"native_type": response_type, "event": data},
                raw=raw,
            )
        if response_type in {"response.failed", "response.incomplete"}:
            return AgentStreamEvent(
                type="error",
                data={"native_type": response_type},
                raw=raw,
            )
        return AgentStreamEvent(
            type=response_type or "run.event",
            data=data,
            raw=raw,
        )

    if native_type == "agent_updated_stream_event":
        agent = getattr(raw, "new_agent", None)
        return AgentStreamEvent(
            type="agent.changed",
            data={"agent": getattr(agent, "name", None)},
            raw=raw,
        )

    if native_type == "run_item_stream_event":
        name = str(getattr(raw, "name", ""))
        if name in {"tool_called", "tool_search_called"}:
            event_type = "tool.called"
        elif name in {"tool_output", "tool_search_output_created"}:
            event_type = "tool.completed"
        elif name in {"handoff_occured", "handoff_occurred"}:
            event_type = "agent.changed"
        else:
            event_type = "run.event"
        return AgentStreamEvent(
            type=event_type,
            data={"name": name, "item": getattr(raw, "item", None)},
            raw=raw,
        )

    return AgentStreamEvent(type=native_type or "run.event", data=raw, raw=raw)
