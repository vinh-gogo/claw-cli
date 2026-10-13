from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Coroutine


@dataclass
class Event:
    pass


@dataclass
class TextDelta(Event):
    text: str


@dataclass
class ThinkingStart(Event):
    pass


@dataclass
class ThinkingDelta(Event):
    text: str


@dataclass
class ThinkingEnd(Event):
    pass


@dataclass
class ToolCallStart(Event):
    call_id: str
    tool: str
    args: dict[str, Any]


@dataclass
class ApprovalRequest(Event):
    call_id: str
    tool: str
    args: dict[str, Any]
    risk_level: str
    reason: str
    diff: str | None = None


@dataclass
class ApprovalResponse(Event):
    call_id: str
    approved: bool
    reason: str = ""


@dataclass
class ToolResultEvent(Event):
    call_id: str
    tool: str
    output: str
    error: str | None = None
    is_error: bool = False


@dataclass
class SayEvent(Event):
    text: str


@dataclass
class VoiceStateEvent(Event):
    state: str  # IDLE, LISTENING, TRANSCRIBING, REVIEW_TRANSCRIPT, THINKING, ACTING, SPEAKING
    details: str = ""


@dataclass
class TranscriptEvent(Event):
    text: str
    confidence: float = 1.0
    auto_send: bool = True


@dataclass
class Final(Event):
    text: str
    usage: dict[str, Any] | None = None


@dataclass
class CancelEvent(Event):
    reason: str = "Cancelled by user"


EventListener = Callable[[Event], Coroutine[Any, Any, None] | None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def subscribe(self, listener: EventListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: EventListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def emit(self, event: Event) -> None:
        for listener in self._listeners:
            try:
                res = listener(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                # Listener failure shouldn't kill the bus
                print(f"[EventBus error] {e}")
