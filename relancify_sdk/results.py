from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ExecutionMode = Literal["hosted", "local"]


@dataclass(frozen=True)
class AgentRunResult:
    """Stable result returned by both hosted and local agent runs."""

    output: Any
    execution: ExecutionMode
    conversation_id: str | None
    usage: Any
    billing: Any
    raw: Any

    @property
    def final_output(self) -> Any:
        """Compatibility alias for the OpenAI Agents SDK result name."""
        return self.output

    @classmethod
    def from_hosted(cls, response: Any) -> "AgentRunResult":
        payload = response if isinstance(response, dict) else {}
        conversation_id = payload.get("conversation_id")
        return cls(
            output=payload.get("output"),
            execution="hosted",
            conversation_id=(
                str(conversation_id) if conversation_id is not None else None
            ),
            usage=payload.get("usage"),
            billing=payload.get("billing"),
            raw=response,
        )

    @classmethod
    def from_local(cls, result: Any) -> "AgentRunResult":
        conversation_id = getattr(result, "conversation_id", None)
        if conversation_id is None:
            conversation_id = getattr(result, "_conversation_id", None)
        return cls(
            output=getattr(result, "final_output", None),
            execution="local",
            conversation_id=(
                str(conversation_id) if conversation_id is not None else None
            ),
            usage=_local_usage(result),
            billing=None,
            raw=result,
        )

    def to_event_data(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "execution": self.execution,
            "conversation_id": self.conversation_id,
            "usage": self.usage,
            "billing": self.billing,
        }


@dataclass(frozen=True)
class AgentStreamEvent:
    """Stable event envelope returned by hosted and local streams."""

    type: str
    data: Any = None
    delta: Any = None
    raw: Any = None


def _local_usage(result: Any) -> dict[str, int] | None:
    totals = {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    found = False
    for response in getattr(result, "raw_responses", ()) or ():
        usage = getattr(response, "usage", None)
        if usage is None:
            continue
        found = True
        for field in totals:
            value = getattr(usage, field, 0)
            if isinstance(value, int):
                totals[field] += value
    return totals if found else None
