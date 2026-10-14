from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import numpy as np
from rich.console import Console
from rich.panel import Panel

from claw.agent.context import AgentContext
from claw.agent.loop import AgentLoop
from claw.agent.prompts import get_system_prompt
from claw.agent.router import route_input
from claw.config import Config, get_config
from claw.events import (
    CancelEvent,
    Final,
    SayEvent,
    ToolCallStart,
    ToolResultEvent,
    VoiceStateEvent,
)
from claw.llm.client import LLMClient
from claw.safety.approval import ApprovalManager
from claw.safety.policy import SafetyPolicy
from claw.safety.sandbox import PathSandbox
from claw.session.audit import AuditLogger
from claw.session.store import SessionStore
from claw.tools import create_default_registry
from claw.ui.console import ConsoleRenderer
from claw.ui.prompt import InteractivePrompt
from claw.ui.status import UIStatus
from claw.voice.player import AudioPlayer
from claw.voice.recorder import AudioRecorder
from claw.voice.stt.faster_whisper import FasterWhisperSTT
from claw.voice.stt.openai_compat import OpenAICompatibleSTT
from claw.voice.tts.edge import EdgeTTSProvider
from claw.voice.tts.system import SystemTTSProvider
from claw.voice.vad import SileroVAD, UtteranceDetector

logger = logging.getLogger("claw.app")


class ClawApp:
    def __init__(self, cfg: Config | None = None, workdir: Path | str | None = None) -> None:
        self.cfg = cfg or get_config()
        self.workdir = Path(workdir) if workdir else Path.cwd()
        self.console = Console()
        self.renderer = ConsoleRenderer(self.console)
        self.status = UIStatus(tts_enabled=(self.cfg.tts.speak_mode != "off"))

        # Set DPI awareness for high-DPI Windows displays
        from claw.winctl.dpi import set_dpi_awareness
        set_dpi_awareness()

        # Initialize LLM & Safety & Tools
        self.llm = LLMClient(self.cfg.llm)
        self.sandbox = PathSandbox(self.workdir)
        from claw.safety.app_policy import AppPolicy
        self.app_policy = AppPolicy(self.cfg.desktop)
        self.safety = SafetyPolicy(self.cfg.safety, self.sandbox, self.app_policy)
        self.approval = ApprovalManager()
        self.tools = create_default_registry()

        from claw.voice.ducking import AudioDucker
        self.ducker = AudioDucker(self.cfg.desktop)

        from claw.winctl.hotkeys import GlobalHotkeyManager
        self.hotkeys = GlobalHotkeyManager()

        # Session & Audit
        self.session_store = SessionStore(self.cfg.session.dir)
        self.audit = AuditLogger(self.cfg.session.audit_file)
        self.current_session_id = self.session_store.create_session_id()

        # Context & Agent Loop
        system_prompt = get_system_prompt(self.workdir)
        self.context = AgentContext(system_prompt=system_prompt)
        self.agent_loop = AgentLoop(
            llm=self.llm,
            ctx=self.context,
            tools=self.tools,
            safety=self.safety,
            approval=self.approval,
            cfg=self.cfg.llm,
        )

        # Voice components
        self.recorder = AudioRecorder(
            sample_rate=self.cfg.audio.sample_rate,
            device=self.cfg.audio.input_device,
        )
        self.vad = SileroVAD(
            sample_rate=self.cfg.audio.sample_rate,
            silence_ms=self.cfg.audio.silence_ms,
            min_speech_ms=self.cfg.audio.min_speech_ms,
            pre_roll_ms=self.cfg.audio.pre_roll_ms,
        )
        self.utterance_detector = UtteranceDetector(self.vad)

        # STT Provider
        if self.cfg.stt.provider == "openai-compatible":
            self.stt: Any = OpenAICompatibleSTT(self.cfg.llm, self.cfg.stt)
        elif self.cfg.stt.provider == "gemma-stt":
            from claw.voice.stt.gemma import Gemma4STTProvider

            self.stt = Gemma4STTProvider(llm_cfg=self.cfg.llm, stt_cfg=self.cfg.stt)
        else:
            self.stt = FasterWhisperSTT(self.cfg.stt)

        # TTS Provider
        if self.cfg.tts.provider == "system":
            self.tts: Any = SystemTTSProvider()
        elif self.cfg.tts.provider == "edge-tts":
            self.tts = EdgeTTSProvider(self.cfg.tts)
        else:
            self.tts = None

        self.player = AudioPlayer(device=self.cfg.audio.output_device)
        self.last_assistant_answer = ""

    async def speak(self, text: str) -> None:
        """Speak out text using configured TTS provider."""
        if not self.status.tts_enabled or not self.tts:
            return

        self.status.voice_state = "SPEAKING"
        try:
            if isinstance(self.tts, EdgeTTSProvider):
                audio_bytes = await self.tts.synthesize(text)
                await self.player.play_audio_bytes(audio_bytes)
            elif isinstance(self.tts, SystemTTSProvider):
                await self.tts.synthesize(text)
        except Exception as e:
            logger.debug(f"TTS playback error: {e}")
        finally:
            self.status.voice_state = "IDLE"

    async def run_turn(self, user_prompt: str) -> str:
        """Execute a full turn for a given user prompt."""
        self.status.voice_state = "THINKING"
        collected_final: list[str] = []

        async for event in self.agent_loop.run_turn(user_prompt):
            self.renderer.render_event(event)

            if isinstance(event, ToolCallStart):
                self.status.voice_state = "ACTING"
                self.status.tool_name = event.tool
            elif isinstance(event, ToolResultEvent):
                self.status.voice_state = "THINKING"
                # Audit log tool execution
                self.audit.log(
                    tool_name=event.tool,
                    args={},
                    risk_level="read" if not event.is_error else "unknown",
                    decision="completed",
                    reason=event.error or "Success",
                    workdir=str(self.workdir),
                    user_input=user_prompt,
                )
            elif isinstance(event, SayEvent):
                # Speak to user
                await self.speak(event.text)
            elif isinstance(event, Final):
                collected_final.append(event.text)
                self.last_assistant_answer = event.text
            elif isinstance(event, CancelEvent):
                self.player.stop()

        self.status.voice_state = "IDLE"
        self.status.tool_name = None

        # Persist session turn
        self.session_store.save_turn(self.current_session_id, self.context.messages)
        return "".join(collected_final)

    async def record_voice_input(self) -> str | None:
        """Record from microphone until an utterance is complete, then transcribe with STT."""
        self.status.voice_state = "LISTENING"
        self.renderer.render_event(VoiceStateEvent("LISTENING"))
        if self.status.speech_mode == "on":
            self.console.print(
                "[dim]   (Đang ở chế độ /speech on · Nhấn '/' hoặc Esc để nhập '/speech off')[/dim]"
            )

        self.ducker.start_duck()
        await self.recorder.start()
        self.utterance_detector.reset()

        complete_pcm: np.ndarray | None = None
        all_frames: list[np.ndarray] = []
        cancelled = False
        slash_typed = False
        try:
            async for frame in self.recorder.stream_frames():
                all_frames.append(frame)
                utterance = self.utterance_detector.process_frame(frame)
                if utterance is not None:
                    complete_pcm = utterance
                    break

                # Check if user pressed Enter to finish, '/' to type command, or Esc to cancel on Windows
                try:
                    import msvcrt

                    while msvcrt.kbhit():
                        ch = msvcrt.getwch()
                        if ch == "\x1b":
                            cancelled = True
                            break
                        if ch == "/":
                            slash_typed = True
                            break
                        if ch in ("\r", "\n"):
                            frames_to_use = (
                                self.utterance_detector.speech_frames
                                if self.utterance_detector.speech_frames
                                else all_frames
                            )
                            if frames_to_use:
                                complete_pcm = np.concatenate(frames_to_use)
                            break
                    if cancelled or slash_typed or complete_pcm is not None:
                        break
                except ImportError:
                    pass
        finally:
            await self.recorder.stop()
            self.ducker.restore_duck()

        if slash_typed:
            self.status.voice_state = "IDLE"
            return "__SLASH_COMMAND__"

        if cancelled:
            self.status.voice_state = "IDLE"
            if self.status.speech_mode == "on":
                return "/speech off"
            return None

        if complete_pcm is None:
            self.status.voice_state = "IDLE"
            return None

        self.status.voice_state = "TRANSCRIBING"
        self.renderer.render_event(VoiceStateEvent("TRANSCRIBING"))

        transcript = await self.stt.transcribe(complete_pcm)
        self.status.voice_state = "IDLE"

        if not transcript.text:
            self.console.print("[dim](Không nhận diện được giọng nói)[/dim]")
            return None

        return transcript.text

    async def run_interactive(self) -> None:
        """Run the interactive voice + text terminal loop."""
        ui_prompt = InteractivePrompt(self.status)

        # Prewarm STT in background
        if hasattr(self.stt, "prewarm"):
            asyncio.create_task(self.stt.prewarm())

        # Welcome banner
        self.console.print(
            Panel.fit(
                "[bold cyan]CLAW CLI[/bold cyan] — Trợ lý dòng lệnh điều khiển bằng giọng nói tiếng Việt\n"
                "[dim]Gõ phím hoặc nhấn [bold yellow]Space[/bold yellow] để nói · [bold]/speech on[/bold] chỉ giọng nói · [bold]/speech off[/bold] chỉ văn bản · [bold]Ctrl+T[/bold] TTS[/dim]",
                border_style="cyan",
            )
        )

        want_voice_recording = False

        def trigger_voice():
            nonlocal want_voice_recording
            if self.status.speech_mode != "off":
                want_voice_recording = True

        def toggle_tts():
            self.status.tts_enabled = not self.status.tts_enabled
            self.console.print(f"\n[dim]TTS: {'Bật' if self.status.tts_enabled else 'Tắt'}[/dim]")

        def cancel_action():
            self.agent_loop.cancel()
            self.player.stop()

        ui_prompt.on_space_empty = trigger_voice
        ui_prompt.on_toggle_tts = toggle_tts
        ui_prompt.on_cancel = cancel_action

        while True:
            try:
                user_text = ""
                if self.status.speech_mode == "on" or (
                    want_voice_recording and self.status.speech_mode != "off"
                ):
                    want_voice_recording = False
                    spoken = await self.record_voice_input()
                    if not spoken:
                        continue

                    if spoken == "__SLASH_COMMAND__":
                        cmd_text = await ui_prompt.get_input(default="/")
                        if not cmd_text:
                            continue
                        routed_cmd = route_input(cmd_text)
                        if routed_cmd.kind in ("speech_off", "speech_on") or cmd_text.lower() in (
                            "exit",
                            "quit",
                            ":q",
                        ):
                            user_text = cmd_text
                        elif self.status.speech_mode == "on":
                            self.console.print(
                                "[yellow]Đang ở chế độ chỉ nhận giọng nói (/speech on). "
                                "Hãy nói vào mic hoặc nhập '/speech off' để chuyển sang văn bản.[/yellow]"
                            )
                            continue
                        else:
                            user_text = cmd_text
                    elif route_input(spoken).kind in ("speech_off", "speech_on"):
                        user_text = spoken
                    else:
                        self.console.print(f"\n🎙 Nhận diện: [bold green]\"{spoken}\"[/bold green]")
                        # Transcript review if enabled
                        if self.cfg.audio.review_transcript:
                            self.console.print("[dim][Enter=Gửi · e=Sửa · /speech off=Tắt mic (tự gửi sau 1.5s)]...[/dim]")
                            # Wait for enter or auto-send timeout
                            try:
                                edited = await asyncio.wait_for(
                                    asyncio.to_thread(input),
                                    timeout=self.cfg.audio.auto_send_ms / 1000.0,
                                )
                                if edited.strip():
                                    spoken = edited.strip()
                            except asyncio.TimeoutError:
                                # Auto-sent
                                pass
                        user_text = spoken
                else:
                    want_voice_recording = False
                    user_text = await ui_prompt.get_input()

                if not user_text:
                    continue

                if user_text.lower() in ("exit", "quit", ":q"):
                    self.console.print("[bold yellow]Tạm biệt![/bold yellow]")
                    break

                if user_text.strip().lower() == "/speech":
                    mode_desc = {
                        "on": "Chỉ nhận giọng nói (/speech on)",
                        "off": "Chỉ nhận văn bản (/speech off)",
                        "hybrid": "Hỗn hợp (Space để nói hoặc gõ văn bản)",
                    }.get(self.status.speech_mode, self.status.speech_mode)
                    self.console.print(
                        f"[cyan]Chế độ hiện tại:[/cyan] [bold]{mode_desc}[/bold]\n"
                        "[dim]Sử dụng: '/speech on' (chỉ nhận giọng nói) hoặc '/speech off' (chỉ nhận văn bản)[/dim]"
                    )
                    continue

                # Route input for meta commands
                routed = route_input(user_text)

                if routed.kind == "speech_on":
                    self.status.speech_mode = "on"
                    want_voice_recording = True
                    self.console.print(
                        "[bold green]🎙 Đã bật chế độ giọng nói (/speech on): Chỉ nhận lệnh bằng giọng nói.[/bold green]"
                    )
                    continue
                elif routed.kind == "speech_off":
                    self.status.speech_mode = "off"
                    want_voice_recording = False
                    self.console.print(
                        "[bold cyan]⌨️ Đã tắt chế độ giọng nói (/speech off): Chỉ nhận lệnh bằng văn bản.[/bold cyan]"
                    )
                    continue
                elif routed.kind == "cancel":
                    self.agent_loop.cancel()
                    self.player.stop()
                    self.console.print("[yellow]Đã huỷ thao tác.[/yellow]")
                    continue
                elif routed.kind == "mute_tts":
                    self.status.tts_enabled = False
                    self.console.print("[dim]Đã tắt âm thanh.[/dim]")
                    continue
                elif routed.kind == "unmute_tts":
                    self.status.tts_enabled = True
                    self.console.print("[dim]Đã bật âm thanh.[/dim]")
                    continue
                elif routed.kind == "repeat":
                    if self.last_assistant_answer:
                        self.console.print(f"\n[italic cyan]🔊 {self.last_assistant_answer}[/italic cyan]")
                        await self.speak(self.last_assistant_answer)
                    else:
                        self.console.print("[dim]Chưa có câu trả lời nào trước đó.[/dim]")
                    continue
                elif routed.kind == "reset":
                    self.context.clear_history()
                    self.current_session_id = self.session_store.create_session_id()
                    self.console.print("[bold green]Đã làm mới phiên hội thoại.[/bold green]")
                    continue

                # Run regular agent turn
                await self.run_turn(user_text)

            except (KeyboardInterrupt, asyncio.CancelledError):
                self.console.print("\n[yellow]Nhấn Ctrl+C lần nữa hoặc gõ 'exit' để thoát.[/yellow]")
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"[bold red]Lỗi hệ thống:[/bold red] {e}")
