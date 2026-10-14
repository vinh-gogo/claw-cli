from __future__ import annotations

from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings

from claw.ui.status import UIStatus


class InteractivePrompt:
    def __init__(self, status: UIStatus | None = None) -> None:
        self.status = status or UIStatus()
        self.history = InMemoryHistory()
        self.bindings = KeyBindings()
        self.on_space_empty: Callable[[], None] | None = None
        self.on_toggle_tts: Callable[[], None] | None = None
        self.on_cancel: Callable[[], None] | None = None

        self._setup_bindings()
        self.session: PromptSession[str] = PromptSession(
            history=self.history,
            key_bindings=self.bindings,
        )

    def _setup_bindings(self) -> None:
        @self.bindings.add("space")
        def _(event):
            buf = event.current_buffer
            # If buffer is empty and not in text-only (/speech off) mode, pressing Space triggers voice recording
            if not buf.text and self.on_space_empty and self.status.speech_mode != "off":
                self.on_space_empty()
                event.app.exit(result="")
            else:
                buf.insert_text(" ")

        @self.bindings.add("c-t")
        def _(event):
            if self.on_toggle_tts:
                self.on_toggle_tts()

        @self.bindings.add("escape")
        def _(event):
            if self.on_cancel:
                self.on_cancel()

    def get_bottom_toolbar(self) -> HTML:
        if self.status.speech_mode == "off":
            state_icon = "⌨️ [Chỉ văn bản | /speech on]"
        elif self.status.speech_mode == "on":
            state_icon = "🎙 [Chỉ giọng nói | /speech off]"
        else:
            state_icon = (
                "🎙 [Nghe: Space | /speech on|off]"
                if self.status.voice_state == "IDLE"
                else f"<b>[{self.status.voice_state}]</b>"
            )
        tts_icon = "🔊 TTS: Bật (Ctrl+T)" if self.status.tts_enabled else "🔇 TTS: Tắt (Ctrl+T)"
        return HTML(f"<style bg='ansiblue' fg='ansiwhite'> {state_icon} | {tts_icon} | Esc: Huỷ | Model: {self.status.model} </style>")

    async def get_input(self, default: str = "") -> str:
        """Prompt user asynchronously for command."""
        text = await self.session.prompt_async(
            HTML("<ansigreen><b>claw ▸</b></ansigreen> "),
            default=default,
            bottom_toolbar=self.get_bottom_toolbar,
        )
        return text.strip()
