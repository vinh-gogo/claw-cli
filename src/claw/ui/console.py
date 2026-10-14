from __future__ import annotations

import json

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from claw.events import (
    CancelEvent,
    Event,
    Final,
    SayEvent,
    TextDelta,
    ToolCallStart,
    ToolResultEvent,
    VoiceStateEvent,
)


class ConsoleRenderer:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self._streaming_text = False
        self._current_stream_buffer: list[str] = []

    def render_event(self, event: Event) -> None:
        if isinstance(event, TextDelta):
            if not self._streaming_text:
                self._streaming_text = True
                self._current_stream_buffer = []
            self._current_stream_buffer.append(event.text)
            self.console.print(event.text, end="")

        elif isinstance(event, ToolCallStart):
            self._flush_stream()
            args_str = json.dumps(event.args, ensure_ascii=False)
            if len(args_str) > 80:
                args_str = args_str[:77] + "..."
            self.console.print(f"\n[bold yellow]🔧 {event.tool}[/bold yellow]({args_str})", end=" ")

        elif isinstance(event, ToolResultEvent):
            self._flush_stream()
            if event.is_error:
                self.console.print(f"[bold red]✘ Lỗi:[/bold red] {event.error}")
            else:
                self.console.print("[bold green]✔ Xong[/bold green]")

            # Preview snippet if available
            if event.output and event.tool not in ("say", "ask_user"):
                lines = event.output.strip().splitlines()
                preview = "\n".join(lines[:6])
                if len(lines) > 6:
                    preview += f"\n... [và {len(lines) - 6} dòng nữa]"
                self.console.print(Panel(preview, title=f"Kết quả {event.tool}", border_style="dim"))

        elif isinstance(event, Final):
            was_streaming = self._streaming_text
            self._flush_stream()
            if event.text and not was_streaming:
                self.console.print("\n")
                self.console.print(Markdown(event.text))
            self.console.print()

        elif isinstance(event, SayEvent):
            self.console.print(f"\n[italic cyan]🔊 \"{event.text}\"[/italic cyan]")

        elif isinstance(event, VoiceStateEvent):
            if event.state == "LISTENING":
                self.console.print(
                    "[bold red]🎙 Đang nghe... (Nói vào mic — tự động chốt câu khi ngừng nói)[/bold red]"
                )
            elif event.state == "TRANSCRIBING":
                self.console.print("[dim]📝 Đang chuyển giọng nói thành văn bản...[/dim]")

        elif isinstance(event, CancelEvent):
            self._flush_stream()
            self.console.print(f"\n[bold red]🛑 {event.reason}[/bold red]\n")

    def _flush_stream(self) -> None:
        if self._streaming_text:
            self._streaming_text = False
            self._current_stream_buffer = []
            self.console.print()
