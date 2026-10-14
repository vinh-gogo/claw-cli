from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text


@dataclass
class UIStatus:
    voice_state: str = "IDLE"  # IDLE, LISTENING, TRANSCRIBING, REVIEW_TRANSCRIPT, THINKING, ACTING, SPEAKING
    tool_name: str | None = None
    tts_enabled: bool = True
    speech_mode: str = "hybrid"  # "hybrid" (Space to talk + text), "on" (voice only), "off" (text only)
    input_device: str = "Mic"
    model: str = "LLM"

    def render_bar(self) -> Text:
        icons = {
            "IDLE": "💤 Nghỉ",
            "LISTENING": "🎙 Đang nghe...",
            "TRANSCRIBING": "📝 Đang nhận diện...",
            "REVIEW_TRANSCRIPT": "👀 Xem lại...",
            "THINKING": "🧠 Đang suy nghĩ...",
            "ACTING": f"🔧 Chạy {self.tool_name or 'tool'}...",
            "SPEAKING": "🔊 Đang đọc...",
        }
        state_str = icons.get(self.voice_state, self.voice_state)
        tts_str = "🔊 TTS: Bật" if self.tts_enabled else "🔇 TTS: Tắt"
        mode_map = {
            "on": "🎙 Chỉ giọng nói (/speech on)",
            "off": "⌨️ Chỉ văn bản (/speech off)",
            "hybrid": "🎙+⌨️ Hỗn hợp",
        }
        mode_str = mode_map.get(self.speech_mode, self.speech_mode)

        t = Text()
        t.append(f"[{state_str}]", style="bold cyan")
        t.append(" · ")
        t.append(mode_str, style="dim")
        t.append(" · ")
        t.append(tts_str, style="dim")
        t.append(" · ")
        t.append(f"Model: {self.model}", style="dim")
        return t
