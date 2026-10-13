# claw-cli — Kế hoạch xây dựng dự án

> **Mục tiêu một câu:** nói vào mic → `claw` nghe, hiểu, tự dùng công cụ (đọc/ghi file, chạy lệnh shell…) để làm việc trong terminal → báo kết quả lại bằng chữ và giọng nói.

|                    |                                                                   |
| ------------------ | ----------------------------------------------------------------- |
| **Tên dự án**      | `claw-cli` (lệnh chạy: `claw`)                                    |
| **LLM backend**    | Server OpenAI-compatible đã có sẵn (`/v1/chat/completions`)       |
| **Phần cần build** | Voice I/O + Agent loop + Tools + Safety + TUI                     |
| **Ngôn ngữ chính** | Tiếng Việt (có thể nói xen tiếng Anh: `git`, `pytest`, `docker`…) |
| **Ước lượng**      | ~4–6 tuần part-time (1 dev), MVP có giọng nói sau ~2 tuần         |

---

## 1. Tổng quan

### 1.1 Goals

- Điều khiển terminal bằng giọng nói tiếng Việt: _"chạy test rồi cho tôi biết file nào lỗi"_.
- Agent loop thật sự: LLM gọi tool → nhận kết quả → tiếp tục đến khi xong.
- An toàn: lệnh nguy hiểm **luôn** phải xác nhận; nhận diện giọng sai không được gây hậu quả không đảo ngược.
- Dùng được cả **gõ phím lẫn nói** trong cùng một phiên (không ép voice-only).
- Chạy tốt trên 1 máy cá nhân: STT chạy local, LLM gọi qua server có sẵn.
- Cài đặt gọn: `pipx install claw-cli` hoặc `uv tool install claw-cli`.

### 1.2 Non-goals (không làm ở MVP)

- Không tự train/fine-tune model.
- Không làm GUI/web; chỉ terminal.
- Không làm đa người dùng, không làm cloud sync.
- Không làm "computer use" (điều khiển chuột/màn hình).
- Không hỗ trợ điều khiển SSH/remote ở MVP.

### 1.3 Ví dụ trải nghiệm mong muốn

```
$ claw
claw ▸ (đang nghe… nhấn Space để bắt đầu nói)

🎙  "Liệt kê các file python trong thư mục này rồi đếm tổng số dòng"
📝  Liệt kê các file python trong thư mục này rồi đếm tổng số dòng   [Enter=gửi · e=sửa · Esc=huỷ]

🔧 glob(pattern="**/*.py")                          ✔ 14 files
🔧 bash(cmd="wc -l $(git ls-files '*.py')")         ✔ auto-approved (read-only)
🤖 Có 14 file Python với tổng cộng 2.318 dòng. File dài nhất là agent/loop.py (412 dòng).
🔊 (đọc to phần tóm tắt)
```

---

## 2. Quyết định kỹ thuật

| Hạng mục              | Lựa chọn đề xuất                                                          | Lý do                                      | Phương án dự phòng                                                             |
| --------------------- | ------------------------------------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------ |
| Ngôn ngữ              | **Python 3.11+**                                                          | Hệ sinh thái audio/STT/VAD tốt nhất        | TypeScript (nếu muốn bundle 1 binary)                                          |
| Quản lý package       | **uv** + `pyproject.toml`                                                 | Nhanh, lock file, dễ publish               | poetry                                                                         |
| CLI framework         | **Typer**                                                                 | Subcommand + help tự sinh                  | Click                                                                          |
| Render terminal       | **Rich**                                                                  | Markdown, spinner, panel, syntax highlight | Textual (Phase 6 nếu cần TUI đầy đủ)                                           |
| Input (gõ + phím tắt) | **prompt_toolkit**                                                        | Keybinding, history, multiline             | readline                                                                       |
| LLM client            | **openai** SDK (`AsyncOpenAI(base_url=...)`)                              | Server đã OpenAI-compatible                | `httpx` thuần                                                                  |
| Thu âm                | **sounddevice** (PortAudio)                                               | Cross-platform, stream callback            | `pyaudio`                                                                      |
| VAD                   | **silero-vad** (ONNX)                                                     | Chính xác, nhẹ, chạy CPU                   | `webrtcvad`                                                                    |
| STT                   | **faster-whisper** (local), model `medium` (CPU) / `large-v3-turbo` (GPU) | Hỗ trợ tiếng Việt, offline                 | PhoWhisper (VinAI), whisper.cpp, hoặc `/v1/audio/transcriptions` nếu server có |
| TTS                   | **edge-tts** (`vi-VN-HoaiMyNeural` / `vi-VN-NamMinhNeural`)               | Miễn phí, giọng Việt tự nhiên              | Piper (offline), `/v1/audio/speech`, `say`/`espeak`                            |
| Wake word (tuỳ chọn)  | **openWakeWord**                                                          | Open-source, train được "hey claw"         | Chỉ dùng push-to-talk                                                          |
| Config                | **TOML** + biến môi trường (`pydantic-settings`)                          | Dễ đọc, có validate                        | YAML                                                                           |
| Test                  | `pytest`, `pytest-asyncio`, `respx`                                       | Mock HTTP/LLM                              | —                                                                              |
| Lint/type             | `ruff`, `mypy`                                                            | —                                          | —                                                                              |

> ⚠️ **Cần xác nhận sớm (Phase 0):** server LLM có hỗ trợ **function/tool calling** (`tools` trong request) và **streaming** hay không. Nếu không có tool calling native → dùng chế độ `tool_mode = "prompt"` (model trả JSON, mình tự parse). Plan đã có đường lui cho cả hai.

---

## 3. Kiến trúc

### 3.1 Luồng dữ liệu tổng thể

```
        ┌──────────┐   audio    ┌───────┐  speech   ┌──────────┐   text
 Mic ──▶│ Recorder │──────────▶ │  VAD  │─────────▶ │   STT    │────────┐
        └──────────┘  16kHz PCM └───────┘  segment  └──────────┘        │
                                                                         ▼
 Bàn phím ─────────────────────────────────────────────────────▶ ┌──────────────┐
                                                                 │ Input Router │
                                                                 └──────┬───────┘
                                                                        │ user message
                                                                        ▼
                         ┌────────────────────────────────────────────────────┐
                         │                    Agent Loop                      │
                         │  messages ─▶ LLM (stream) ─▶ tool_calls?           │
                         │      ▲                           │ yes             │
                         │      │                     ┌─────▼──────┐          │
                         │      └──── tool results ◀──│ Permission │          │
                         │                            │  + Tools   │          │
                         │                            └────────────┘          │
                         └───────────────┬───────────────────────┬────────────┘
                                         │ stream text           │ say(text)
                                         ▼                       ▼
                                   ┌──────────┐            ┌──────────┐
                                   │ Rich UI  │            │   TTS    │──▶ Loa
                                   └──────────┘            └──────────┘
```

### 3.2 State machine của phiên voice

```
          ┌────────────────────────── CANCEL (Esc / "dừng" / "huỷ") ──────────────────────────┐
          ▼                                                                                   │
        IDLE ──(Space / wake word)──▶ LISTENING ──(VAD hết tiếng)──▶ TRANSCRIBING             │
          ▲                                                              │                    │
          │                                                              ▼                    │
          │                                                    REVIEW_TRANSCRIPT (tuỳ chọn)   │
          │                                                              │ Enter / auto 1.5s  │
          │                                                              ▼                    │
          │                                                          THINKING ◀──┐            │
          │                                                              │       │ tool result│
          │                                                              ▼       │            │
          │                                                           ACTING ────┘            │
          │                                                       (AWAIT_APPROVAL nếu cần)    │
          │                                                              │ final answer       │
          │                                                              ▼                    │
          └─────────────────────────────────────────────────────── SPEAKING ─────────────────┘
```

Quy tắc: **mọi trạng thái đều có thể bị huỷ**; huỷ phải dừng được tool đang chạy (kill process group) và dừng TTS ngay.

### 3.3 Nguyên tắc thiết kế

1. **Provider interface cho mọi thứ I/O** (`STTProvider`, `TTSProvider`, `LLMClient`) → đổi backend chỉ cần đổi config.
2. **Core agent không biết gì về audio** — nhận text, trả event stream. Nhờ vậy test được không cần mic.
3. **Event-driven:** agent phát `Event` (`TextDelta`, `ToolCallStart`, `ToolResult`, `ApprovalRequest`, `Final`…), UI và TTS cùng subscribe.
4. **Async toàn bộ** (`asyncio`): ghi âm, gọi LLM, TTS, chạy tool song song, không block UI.
5. **Mặc định an toàn** (deny-by-default cho thứ chưa biết).

---

## 4. Cấu trúc thư mục

```
claw-cli/
├── pyproject.toml
├── README.md
├── .env.example                 # CLAW_BASE_URL, CLAW_API_KEY (KHÔNG commit .env thật)
├── .gitignore
├── src/claw/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                   # Typer app: claw, ask, listen, doctor, devices, resume…
│   ├── config.py                # pydantic settings, load TOML + env
│   ├── events.py                # dataclass Event types + EventBus
│   ├── app.py                   # orchestration: nối input → agent → output
│   │
│   ├── llm/
│   │   ├── client.py            # AsyncOpenAI wrapper, retry, streaming, extra headers
│   │   ├── schema.py            # Message, ToolCall, Usage
│   │   └── prompt_tools.py      # fallback tool-calling bằng JSON (khi server không hỗ trợ)
│   │
│   ├── agent/
│   │   ├── loop.py              # vòng lặp LLM ⇄ tools
│   │   ├── context.py           # quản lý history, token budget, nén context
│   │   ├── prompts.py           # system prompt (vi/en)
│   │   └── router.py            # phân loại "lệnh meta" vs "yêu cầu cho agent"
│   │
│   ├── tools/
│   │   ├── base.py              # Tool ABC, registry, JSON schema
│   │   ├── fs.py                # read_file, write_file, edit_file, list_dir, glob, grep
│   │   ├── shell.py             # bash (timeout, process group, truncate output)
│   │   ├── web.py               # web_fetch (Phase 6)
│   │   ├── say.py               # say(text): nội dung để đọc to
│   │   └── ask_user.py          # hỏi lại người dùng khi mơ hồ
│   │
│   ├── safety/
│   │   ├── policy.py            # phân loại rủi ro: read / write / exec / dangerous
│   │   ├── patterns.py          # deny/allow regex cho shell
│   │   ├── sandbox.py           # chuẩn hoá path, chặn thoát workdir
│   │   └── approval.py          # luồng xin phép (phím / giọng)
│   │
│   ├── voice/
│   │   ├── devices.py           # liệt kê/chọn mic, loa
│   │   ├── recorder.py          # sounddevice InputStream → queue
│   │   ├── vad.py               # silero-vad: phát hiện bắt đầu/kết thúc câu
│   │   ├── stt/
│   │   │   ├── base.py
│   │   │   ├── faster_whisper.py
│   │   │   └── openai_compat.py
│   │   ├── tts/
│   │   │   ├── base.py
│   │   │   ├── edge.py
│   │   │   ├── piper.py
│   │   │   └── system.py
│   │   ├── player.py            # phát audio, hỗ trợ stop ngay (barge-in)
│   │   ├── wakeword.py          # (Phase 4)
│   │   └── commands.py          # từ khoá meta: "dừng", "huỷ", "đồng ý"…
│   │
│   ├── ui/
│   │   ├── console.py           # Rich renderer cho Event
│   │   ├── prompt.py            # prompt_toolkit session + keybindings
│   │   └── status.py            # thanh trạng thái: 🎙 / 🧠 / 🔧 / 🔊
│   │
│   └── session/
│       ├── store.py             # lưu JSONL transcript
│       └── audit.py             # log mọi tool call + quyết định approval
│
├── tests/
│   ├── unit/
│   ├── integration/             # fake OpenAI server
│   ├── fixtures/audio/          # wav tiếng Việt mẫu + expected text
│   └── e2e/
└── docs/
    ├── architecture.md
    ├── voice-tuning.md
    └── security.md
```

---

## 5. Thiết kế chi tiết từng module

### 5.1 LLM client

**Yêu cầu**

- `base_url` + `api_key` lấy từ env/config, **không hardcode**.
- Header bổ sung: `ngrok-skip-browser-warning: true` (tránh trang cảnh báo của ngrok chen vào response).
- Streaming SSE, parse `delta.content` và `delta.tool_calls` (gom từng mảnh arguments).
- Retry với exponential backoff cho `429/502/503/504` và lỗi kết nối (ngrok hay chập chờn).
- Timeout tách riêng: `connect=10s`, `first_token=60s`, `total=300s`.
- Tự lấy danh sách model từ `GET /v1/models` khi `model = "auto"`.

**Khung code**

```python
# src/claw/llm/client.py
from openai import AsyncOpenAI

class LLMClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.client = AsyncOpenAI(
            base_url=cfg.base_url,
            api_key=cfg.api_key or "not-needed",
            default_headers=cfg.extra_headers,   # {"ngrok-skip-browser-warning": "true"}
            timeout=cfg.timeout_s,
            max_retries=cfg.max_retries,
        )

    async def stream(self, messages, tools=None):
        stream = await self.client.chat.completions.create(
            model=self.cfg.model,
            messages=messages,
            tools=tools or None,
            temperature=self.cfg.temperature,
            stream=True,
        )
        async for chunk in stream:
            yield chunk
```

**Chế độ tool calling**

| `tool_mode` | Khi nào dùng              | Cách hoạt động                                                                                                            |
| ----------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `native`    | Server hỗ trợ `tools`     | Dùng đúng chuẩn OpenAI function calling                                                                                   |
| `prompt`    | Server/model không hỗ trợ | System prompt mô tả tool, model trả `{"tool": "...", "args": {...}}`; parse + validate bằng pydantic, retry khi JSON hỏng |

`claw doctor` sẽ tự test và đề xuất chế độ phù hợp.

### 5.2 Agent loop

```python
# src/claw/agent/loop.py  (pseudocode)
async def run_turn(self, user_text: str):
    self.ctx.add_user(user_text)
    for step in range(self.cfg.max_steps):            # mặc định 25
        msg = await self.llm_collect(self.ctx.messages, self.tools.schemas())
        self.ctx.add_assistant(msg)

        if not msg.tool_calls:
            yield Final(text=msg.content)
            return

        for call in msg.tool_calls:                   # có thể chạy song song nếu tool "read"
            yield ToolCallStart(call)
            decision = await self.safety.check(call)  # allow / ask / deny
            if decision.ask:
                yield ApprovalRequest(call, decision.reason)
                decision = await self.approval.wait()
            if decision.denied:
                result = ToolResult.denied(decision.reason)
            else:
                result = await self.tools.run(call, cancel=self.cancel_token)
            self.ctx.add_tool_result(call.id, result.for_llm())
            yield ToolResultEvent(call, result)
    yield Final(text="Đã đạt giới hạn số bước; dừng để tránh vòng lặp.")
```

**Chi tiết quan trọng**

- `max_steps`, `max_tool_output_chars` (cắt ~8–10k ký tự, ghi rõ `…[đã cắt N ký tự]`).
- **Cancel token** xuyên suốt: Esc / "dừng" huỷ được cả stream LLM lẫn tool đang chạy.
- **Context management:** theo dõi số token ước lượng; khi >75% cửa sổ, nén các lượt cũ thành tóm tắt (gọi LLM tóm tắt) nhưng giữ nguyên system prompt + vài lượt gần nhất.
- Phát hiện **vòng lặp vô ích** (cùng tool + cùng args ≥3 lần liên tiếp) → dừng và hỏi người dùng.
- Mọi lỗi tool trả về cho LLM dưới dạng text có cấu trúc để model tự sửa.

### 5.3 Tools (MVP)

| Tool                               | Mô tả                     | Mức rủi ro | Ghi chú                               |
| ---------------------------------- | ------------------------- | ---------- | ------------------------------------- |
| `list_dir(path)`                   | Liệt kê thư mục           | read       | Trong workdir                         |
| `read_file(path, offset?, limit?)` | Đọc file text             | read       | Giới hạn kích thước, phát hiện binary |
| `glob(pattern)`                    | Tìm file theo mẫu         | read       | Tôn trọng `.gitignore`                |
| `grep(pattern, path?)`             | Tìm nội dung              | read       | Dùng `ripgrep` nếu có                 |
| `write_file(path, content)`        | Tạo/ghi đè file           | write      | Hiện diff trước khi hỏi               |
| `edit_file(path, old, new)`        | Thay thế chính xác 1 đoạn | write      | Fail nếu `old` không duy nhất         |
| `bash(cmd, timeout?)`              | Chạy lệnh shell           | exec       | Phân tích lệnh để xếp mức rủi ro      |
| `say(text)`                        | Nội dung sẽ được đọc to   | none       | Chỉ 1–2 câu ngắn gọn                  |
| `ask_user(question, options?)`     | Hỏi lại khi mơ hồ         | none       | Tránh đoán bừa khi nghe nhầm          |

**Định nghĩa tool (ví dụ)**

```python
class BashTool(Tool):
    name = "bash"
    description = "Chạy một lệnh shell trong thư mục làm việc hiện tại."
    risk = "exec"

    class Args(BaseModel):
        cmd: str
        timeout: int = Field(60, ge=1, le=600)

    async def run(self, args: Args, ctx: ToolContext) -> ToolResult:
        proc = await asyncio.create_subprocess_shell(
            args.cmd, cwd=ctx.workdir, env=ctx.scrubbed_env(),
            stdout=PIPE, stderr=STDOUT, start_new_session=True,   # để kill cả process group
        )
        ...
```

**Tool `say`** — cách giải quyết bài toán "đừng đọc cả đoạn code dài":

- System prompt yêu cầu: _kết thúc mỗi lượt bằng một lần gọi `say("…")` với 1–2 câu tóm tắt tự nhiên bằng tiếng Việt_.
- Phần chi tiết (bảng, code, log) chỉ hiển thị trên màn hình.
- Fallback nếu model không gọi `say`: lấy 1–2 câu đầu của câu trả lời, bỏ code block/URL/đường dẫn dài.

### 5.4 Safety & permission (phần quan trọng nhất của dự án voice)

**Vì sao cần đặc biệt cẩn thận:** STT có thể nghe nhầm ("xoá thư mục _build_" → "xoá thư mục _bill_"), và tiếng ồn/người khác nói cũng có thể kích hoạt.

**4 mức rủi ro**

| Mức         | Ví dụ                                                                                                                                           | Hành vi mặc định                                           |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `read`      | `ls`, `cat`, `git status`, `grep`, `pytest --collect-only`                                                                                      | Tự chạy                                                    |
| `write`     | ghi/sửa file trong workdir, `git add`, `npm install`                                                                                            | Hỏi (xác nhận được bằng giọng nói)                         |
| `exec`      | chạy script/test/build, `git commit`, lệnh không nhận diện được                                                                                 | Hỏi (xác nhận được bằng giọng nói)                         |
| `dangerous` | `rm -rf`, `sudo`, `git push --force`, `git reset --hard`, `chmod -R`, `curl … \| sh`, `dd`, `mkfs`, ghi ra ngoài workdir, đụng `~/.ssh`, `.env` | **Chỉ xác nhận bằng bàn phím** (gõ `yes`) hoặc bị chặn hẳn |

**Cơ chế**

1. **Phân loại lệnh shell** bằng `shlex` + bảng allowlist/denylist (regex trong `patterns.py`); gặp pipe, `&&`, `;`, `$(...)`, redirect `>` → xét từng đoạn, lấy mức cao nhất.
2. **Sandbox đường dẫn:** `Path.resolve()` rồi kiểm tra nằm trong `workdir` (chặn `..`, symlink thoát ra ngoài).
3. **Môi trường sạch:** loại biến chứa `KEY`, `TOKEN`, `SECRET`, `PASSWORD` khỏi env của subprocess.
4. **Timeout + giới hạn output** cho mọi tool.
5. **Xác nhận bằng giọng nói** chỉ chấp nhận khi:
   - câu trả lời nằm trong tập hẹp (`đồng ý / ok / có / làm đi` vs `không / thôi / huỷ / dừng`),
   - độ tin cậy STT ≥ ngưỡng,
   - **và** hành động không thuộc mức `dangerous`.
6. **Hiển thị trước khi hỏi:** lệnh đầy đủ, hoặc diff cho file; đọc to tóm tắt ngắn ("Tôi sắp chạy `pytest -x`, đồng ý không?").
7. **Chế độ `--yolo`** (tắt hỏi mức write/exec) phải bật tường minh, vẫn **không** bỏ qua `dangerous`.
8. **Audit log** (`audit.jsonl`): thời gian, transcript gốc, tool call, quyết định, ai/cách duyệt.

**Bảo mật server LLM**

- URL ngrok là endpoint công khai: ai biết URL đều gọi được. Nên bật xác thực (API key / basic-auth ở lớp ngrok hoặc ở server) và lưu key trong `.env`/keyring, **không commit**.
- Không in API key ra log; mask khi `claw doctor` hiển thị cấu hình.

### 5.5 Voice input

**Thu âm (`recorder.py`)**

- `sounddevice.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=512)` → đẩy frame vào `asyncio.Queue`.
- Liệt kê/chọn thiết bị: `claw devices`, `--input-device`.
- Xử lý lỗi quyền mic (macOS: cấp quyền cho Terminal/iTerm; Linux: `portaudio19-dev`; Windows: Privacy → Microphone).

**3 chế độ kích hoạt (`audio.input_mode`)**

| Chế độ              | Cách dùng                                                              | Phase |
| ------------------- | ---------------------------------------------------------------------- | ----- |
| `toggle` (mặc định) | Nhấn **Space** để bắt đầu; tự dừng khi im lặng (VAD) hoặc nhấn lần nữa | 3     |
| `hands-free`        | Luôn nghe; VAD tự cắt câu                                              | 4     |
| `wake-word`         | Nói "hey claw" rồi ra lệnh                                             | 4     |

> Terminal không báo "nhả phím" đáng tin cậy nên **không dùng giữ-để-nói (hold-to-talk) làm mặc định**; dùng toggle + VAD. Có thể thêm hold-to-talk qua `pynput` như tuỳ chọn.

**VAD (`vad.py`)**

- silero-vad, ngưỡng `speech_prob > 0.5`.
- Tham số: `min_speech_ms=250`, `silence_ms=900` (kết thúc câu), `pre_roll_ms=300` (giữ lại đầu câu để không mất chữ đầu), `max_record_s=30`.
- Đầu ra: một mảng PCM của đúng 1 câu nói.

**STT (`stt/`)**

```python
class STTProvider(Protocol):
    async def transcribe(self, pcm: np.ndarray, sample_rate: int, language: str = "vi") -> Transcript: ...

@dataclass
class Transcript:
    text: str
    language: str
    confidence: float      # từ avg_logprob / no_speech_prob
    segments: list[Segment]
```

- **faster-whisper:** `WhisperModel("medium", device="auto", compute_type="int8")`; tải model **lazy + prewarm** khi khởi động (chạy nền) để lần nói đầu không bị trễ.
- **Gợi ý độ chính xác tiếng Việt:**
  - `language="vi"` cố định (không auto-detect, nhanh và ít nhầm hơn).
  - `initial_prompt` chứa từ vựng hay dùng: _"git, commit, pytest, docker, npm, thư mục, tệp tin, chạy test…"_ → giúp nhận đúng thuật ngữ kỹ thuật xen tiếng Anh.
  - Lọc ảo giác của Whisper khi im lặng (`no_speech_prob` cao, câu lặp, "Cảm ơn các bạn đã xem video"…).
  - Nếu `medium` vẫn chưa đạt: thử **PhoWhisper** (VinAI, tinh chỉnh cho tiếng Việt) hoặc `large-v3-turbo` nếu có GPU.
- **Provider thay thế:** `openai-compatible` gọi `POST /v1/audio/transcriptions` nếu server của bạn có cung cấp.

**Bước xem lại transcript (`REVIEW_TRANSCRIPT`)**

- Hiện văn bản vừa nhận diện, **tự gửi sau 1.5s** nếu không can thiệp (cấu hình được), `e` để sửa, `Esc` để huỷ.
- Nếu `confidence` thấp hoặc lệnh có vẻ nguy hiểm → **không** tự gửi, đợi Enter.

**Lệnh meta bằng giọng (`commands.py`)**, xử lý **trước** khi gửi cho LLM, khớp chính xác/gần đúng:

| Nói                        | Hành động                                           |
| -------------------------- | --------------------------------------------------- |
| "dừng" / "thôi" / "huỷ"    | Huỷ lượt hiện tại, tắt tiếng                        |
| "đồng ý" / "ok" / "làm đi" | Duyệt yêu cầu đang chờ (nếu không phải `dangerous`) |
| "không" / "đừng"           | Từ chối yêu cầu đang chờ                            |
| "nói lại" / "lặp lại"      | Đọc lại câu trả lời gần nhất                        |
| "xoá phiên" / "làm mới"    | Reset context                                       |
| "im lặng" / "bật tiếng"    | Tắt/bật TTS                                         |

### 5.6 Voice output (TTS)

```python
class TTSProvider(Protocol):
    def synthesize_stream(self, text: str) -> AsyncIterator[bytes]: ...
```

- **edge-tts** mặc định: `vi-VN-HoaiMyNeural` (nữ) / `vi-VN-NamMinhNeural` (nam). Cần internet; đây là API không chính thức nên luôn có fallback.
- **Piper** (offline) làm fallback; `system` (`say`/`espeak-ng`/SAPI) là phương án cuối.
- **Đọc theo câu:** tách câu từ stream text, tổng hợp và phát câu đầu ngay khi có → giảm độ trễ cảm nhận.
- **Chuẩn hoá văn bản trước khi đọc:** bỏ markdown, code block, URL dài; đổi đường dẫn thành tên file ngắn; đọc số/đơn vị tự nhiên.
- **Chống vòng lặp tiếng vọng (echo):** mặc định _half-duplex_ — tắt thu âm khi đang phát; chỉ bật **barge-in** (nói đè để ngắt TTS) khi dùng tai nghe.
- `player.stop()` phải dừng gần như tức thì (dùng stream có thể abort).

### 5.7 UI/UX terminal

- **Rich:** panel cho tool call (tên + tham số rút gọn + trạng thái ✔/✘/⏳), syntax highlight cho code/diff, Markdown cho câu trả lời.
- **Thanh trạng thái** cuối màn hình: `🎙 listening · 🧠 thinking · 🔧 bash · 🔊 speaking · mic: MacBook Pro Mic · model: …`.
- **prompt_toolkit:** gõ bình thường hoặc nhấn Space (khi ô nhập trống) để chuyển sang nói; history, multiline (`Alt+Enter`).
- **Phím tắt:** `Space` nói · `Esc` huỷ · `Ctrl+C` thoát an toàn · `Ctrl+L` clear · `Ctrl+T` bật/tắt TTS · `Tab` đổi chế độ nghe.
- Chế độ **`--no-color` / `--json`** cho script (đầu ra có cấu trúc, không TTS/mic).

### 5.8 Cấu hình

`~/.config/claw/config.toml` (ghi đè bằng env `CLAW_*` và flag CLI):

```toml
[llm]
base_url   = "https://<your-subdomain>.ngrok-free.dev/v1"   # hoặc CLAW_BASE_URL
api_key_env = "CLAW_API_KEY"
model      = "auto"                  # lấy từ GET /v1/models
temperature = 0.2
tool_mode  = "native"                # native | prompt
max_steps  = 25
timeout_s  = 120
extra_headers = { "ngrok-skip-browser-warning" = "true" }

[stt]
provider     = "faster-whisper"      # faster-whisper | openai-compatible
model        = "medium"
language     = "vi"
device       = "auto"
compute_type = "int8"
initial_prompt = "git, commit, pytest, docker, npm, thư mục, tệp tin"

[tts]
provider   = "edge-tts"              # edge-tts | piper | system | openai-compatible | off
voice      = "vi-VN-HoaiMyNeural"
speak_mode = "summary"               # summary | full | off
barge_in   = false

[audio]
input_device = "default"
sample_rate  = 16000
input_mode   = "toggle"              # toggle | hands-free | wake-word
silence_ms   = 900
review_transcript = true
auto_send_ms = 1500

[safety]
workdir_only   = true
auto_approve   = ["read"]
voice_confirm  = ["write", "exec"]
keyboard_only  = ["dangerous"]
yolo           = false

[session]
dir = "~/.local/share/claw/sessions"
```

### 5.9 Session & logging

- Mỗi phiên lưu `sessions/<yyyymmdd-hhmmss>.jsonl` (message, tool call, kết quả, usage).
- `claw resume [id]` nạp lại phiên; `claw sessions` liệt kê.
- Audio thô **không lưu** theo mặc định (riêng tư); bật `--save-audio` khi debug.
- Log kỹ thuật: `structlog`/`logging` ra file xoay vòng, `--verbose` ra màn hình.

### 5.10 System prompt (bản nháp)

```text
Bạn là claw, trợ lý dòng lệnh điều khiển bằng giọng nói. Bạn đang chạy trong terminal
của người dùng, thư mục làm việc: {workdir}. Hệ điều hành: {os}. Shell: {shell}.

Nguyên tắc:
1. Dùng tool để thực sự làm việc; đừng chỉ mô tả. Kiểm tra kết quả trước khi báo xong.
2. Đầu vào đến từ nhận diện giọng nói nên có thể sai chính tả hoặc nghe nhầm tên file/lệnh.
   Nếu yêu cầu mơ hồ hoặc liên quan hành động khó hoàn tác, dùng ask_user để xác nhận trước.
3. Ưu tiên lệnh chỉ-đọc để tìm hiểu trước khi sửa/xoá.
4. Không bao giờ chạy lệnh phá huỷ nếu người dùng không nói rõ.
5. Trả lời ngắn gọn bằng tiếng Việt. Cuối mỗi lượt, gọi say("…") với 1–2 câu tóm tắt
   tự nhiên, không chứa code, URL hay đường dẫn dài.
6. Giữ nguyên thuật ngữ kỹ thuật tiếng Anh (git, docker, commit…).
```

---

## 6. Roadmap theo phase

> Mỗi phase kết thúc bằng một **demo chạy được** và **Definition of Done (DoD)**. Không sang phase sau khi chưa xong DoD.

### Phase 0 — Khởi tạo & kiểm chứng server (0.5–1 ngày)

**Việc cần làm**

- [ ] Khởi tạo repo, `uv init`, `pyproject.toml`, `ruff`, `mypy`, `pytest`, pre-commit, GitHub Actions (lint + test).
- [ ] `.gitignore` (có `.env`), `.env.example` với placeholder.
- [ ] Tạo `.env` thật (không commit): `CLAW_BASE_URL=https://snowcapped-denice-unprudent.ngrok-free.dev/v1`.
- [ ] Spike script `scripts/probe_llm.py` kiểm tra:
  - [ ] `GET /v1/models` trả về danh sách model, ghi lại tên model.
  - [ ] Chat completion thường (không stream).
  - [ ] Streaming SSE.
  - [ ] **Tool calling native** có hoạt động (`tools=[…]` → trả `tool_calls`)?
  - [ ] Tiếng Việt: chất lượng trả lời, độ trễ token đầu (TTFT).
  - [ ] Có `/v1/audio/transcriptions` và `/v1/audio/speech` không (để tận dụng nếu có).
- [ ] Ghi kết quả vào `docs/llm-probe.md` → **quyết định `tool_mode`**.

**Lệnh thử nhanh**

```bash
curl -s "$CLAW_BASE_URL/models" \
  -H "Authorization: Bearer ${CLAW_API_KEY:-x}" \
  -H "ngrok-skip-browser-warning: true" | jq .
```

**DoD:** có tài liệu kết quả probe; biết rõ server hỗ trợ gì; repo chạy được CI rỗng.

---

### Phase 1 — Agent text-only (2–3 ngày)

_Chưa có giọng nói. Chứng minh vòng lặp agent chạy đúng trước._

- [ ] `config.py`: load TOML + env + flag.
- [ ] `llm/client.py`: streaming + retry + extra headers.
- [ ] `events.py`, `agent/loop.py`, `agent/context.py`, `agent/prompts.py`.
- [ ] `tools/base.py` + registry + sinh JSON schema từ pydantic.
- [ ] Tool đầu tiên: `list_dir`, `read_file`, `bash` (chưa có safety, chỉ chạy trong thư mục thử nghiệm).
- [ ] `ui/console.py` render stream + tool call; `cli.py`: `claw ask "…"` và `claw chat` (REPL).
- [ ] Unit test cho loop với **fake LLM** (kịch bản scripted).
- [ ] (nếu cần) `llm/prompt_tools.py` cho `tool_mode = "prompt"`.

**Demo:** `claw ask "liệt kê file trong thư mục này và đọc README"` → thấy chuỗi tool call và câu trả lời.

**DoD:** vòng lặp đa bước ổn định; Ctrl+C dừng sạch; test xanh.

---

### Phase 2 — Bộ tool đầy đủ + Safety (3–4 ngày)

- [ ] Hoàn thiện tools: `write_file`, `edit_file`, `glob`, `grep`, `ask_user`, `say`.
- [ ] `safety/policy.py`, `patterns.py`, `sandbox.py`, `approval.py`.
- [ ] UI xin phép: panel hiển thị lệnh/diff, nhận `y/n/a(lways this session)` bằng bàn phím.
- [ ] Timeout, kill process group, cắt output, scrub env.
- [ ] `session/store.py` + `audit.py`; `claw resume`.
- [ ] Bộ **test an toàn** (xem mục 7): ≥50 lệnh mẫu được phân loại đúng; thử path traversal/symlink.
- [ ] Nén context khi gần đầy.

**Demo:** yêu cầu agent sửa một file và chạy test; thấy diff + xin phép; `rm -rf` bị chặn/đòi gõ tay.

**DoD:** không có đường nào ghi/chạy lệnh ngoài chính sách; audit log đầy đủ.

---

### Phase 3 — Giọng nói vào: Push-to-talk (3–4 ngày) ⭐ _mốc MVP voice_

- [ ] `voice/devices.py` + `claw devices`.
- [ ] `voice/recorder.py` (sounddevice) + `voice/vad.py` (silero).
- [ ] `voice/stt/faster_whisper.py` + prewarm nền + `initial_prompt`.
- [ ] Tích hợp phím `Space` (toggle) vào prompt_toolkit.
- [ ] `REVIEW_TRANSCRIPT` + auto-send + sửa tay.
- [ ] `voice/commands.py`: lệnh meta ("dừng", "đồng ý", "không").
- [ ] Xác nhận bằng giọng cho mức `write`/`exec`.
- [ ] `claw doctor`: kiểm tra mic (đo mức âm), STT (đọc 1 câu mẫu), LLM, ngrok latency.
- [ ] Đo **WER** trên bộ ≥30 câu lệnh tiếng Việt thu sẵn (xem mục 7.3).

**Demo:** nhấn Space, nói _"đọc file readme rồi tóm tắt cho tôi"_ → chạy đúng.

**DoD:** WER trên bộ lệnh ≤ ~15% (mục tiêu; điều chỉnh sau khi đo thực tế); độ trễ "nói xong → bắt đầu gọi LLM" ≤ 2s trên máy mục tiêu; không mất chữ đầu câu.

---

### Phase 4 — Hands-free & Wake word (3–4 ngày, tuỳ chọn)

- [ ] Chế độ `hands-free`: luôn nghe + VAD; chống kích hoạt nhầm (bỏ qua câu < 0.6s, hoặc nhỏ hơn ngưỡng năng lượng).
- [ ] `wakeword.py` với openWakeWord ("hey claw"); cửa sổ lắng nghe 8s sau khi kích hoạt.
- [ ] Tạm dừng nghe khi đang `ACTING`/`SPEAKING` (tránh tự nghe chính mình).
- [ ] Chỉ báo trạng thái rõ ràng (🎙 đang nghe) để người dùng biết mic đang mở.
- [ ] Phím tắt tắt/mở mic nhanh (mute cứng).

**DoD:** chạy 30 phút ở phòng yên tĩnh không có kích hoạt nhầm gây hành động; mic-mute hoạt động tức thì.

---

### Phase 5 — Giọng nói ra: TTS (2–3 ngày)

- [ ] `tts/base.py`, `tts/edge.py`, `tts/system.py` (fallback), `tts/piper.py` (offline, tuỳ chọn).
- [ ] `voice/player.py` với `stop()` tức thì.
- [ ] Tách câu + phát streaming; chuẩn hoá văn bản trước khi đọc.
- [ ] Tool `say` + fallback tóm tắt tự động; `speak_mode = summary|full|off`.
- [ ] Half-duplex (tắt mic khi phát); `barge_in` tuỳ chọn khi dùng tai nghe.
- [ ] Đọc to yêu cầu xác nhận ("Tôi sắp chạy …, đồng ý không?").
- [ ] Cache TTS cho câu cố định (xác nhận, lỗi thường gặp).

**Demo:** hội thoại hoàn chỉnh nói ↔ nghe, ngắt được bằng "dừng".

**DoD:** độ trễ "có câu trả lời → nghe tiếng đầu tiên" ≤ 1.5s; "dừng" tắt tiếng < 300ms.

---

### Phase 6 — Trải nghiệm & mở rộng (3–4 ngày)

- [ ] Status bar hoàn chỉnh, theme sáng/tối, `--json` mode.
- [ ] `web_fetch` (chỉ domain cho phép) và tool đọc PDF/ảnh (tuỳ chọn).
- [ ] **Bộ nhớ dài hạn nhẹ:** file `CLAW.md` ở workdir / `~/.config/claw/memory.md` được nạp vào system prompt (sở thích, quy ước dự án).
- [ ] **Profile/skill:** "chế độ git", "chế độ docker"… = tập prompt + tool allowlist riêng.
- [ ] Hỗ trợ **MCP client** (cắm thêm tool bên ngoài).
- [ ] Tự động sửa lỗi nhận diện: từ điển cá nhân (`~/.config/claw/vocab.txt` → đưa vào `initial_prompt` và hậu xử lý).
- [ ] i18n prompt (vi/en) và tự nhận ngôn ngữ nói.

**DoD:** dùng hằng ngày không vướng; có tài liệu cho từng tính năng.

---

### Phase 7 — Hardening, đóng gói & phát hành (3–4 ngày)

- [ ] Review bảo mật theo `docs/security.md` (prompt injection từ nội dung file/web, tool output độc hại).
- [ ] Chạy thử trên macOS / Linux / Windows (hoặc WSL); ghi rõ phần chưa hỗ trợ.
- [ ] Kiểm thử soak: phiên 1 giờ không rò bộ nhớ, không treo mic.
- [ ] Đóng gói: `uv build`, publish PyPI (hoặc chỉ GitHub release), `pipx install`.
- [ ] README: cài đặt, cấu hình, video/gif demo, Troubleshooting (mic, quyền, ngrok).
- [ ] Release `v0.1.0`; gắn cờ "experimental" cho wake-word và `--yolo`.

---

### Tổng quan lịch (1 dev, part-time)

| Tuần | Nội dung                             | Mốc                                |
| ---- | ------------------------------------ | ---------------------------------- |
| 1    | Phase 0 + Phase 1 + phần đầu Phase 2 | Agent text chạy được               |
| 2    | Hoàn thành Phase 2 + Phase 3         | **MVP nói → làm việc**             |
| 3    | Phase 5 (TTS) + tinh chỉnh STT       | **Hội thoại hai chiều bằng giọng** |
| 4    | Phase 4 (hands-free/wake-word)       | Rảnh tay                           |
| 5    | Phase 6                              | Trải nghiệm hoàn thiện             |
| 6    | Phase 7 + buffer                     | `v0.1.0`                           |

> Nếu muốn nhanh nhất: làm **0 → 1 → 2 → 3 → 5** (bỏ Phase 4), được sản phẩm dùng thật trong ~3 tuần.

---

## 7. Chiến lược kiểm thử

### 7.1 Unit test

- `safety/policy`: bảng test lệnh → mức rủi ro (≥50 case: `ls`, `rm -rf /`, `git push --force`, `echo hi > /etc/hosts`, `cat a | sh`, `$(rm -rf ~)`, v.v.).
- `sandbox`: `../../etc/passwd`, symlink ra ngoài, đường dẫn tuyệt đối, Unicode lạ.
- `tools/*`: edge case (file lớn, binary, không tồn tại, `edit_file` mơ hồ).
- `voice/commands`: biến thể phát âm/chính tả của lệnh meta.
- Parser stream tool_calls bị cắt thành nhiều mảnh.

### 7.2 Integration test

- **Fake OpenAI server** (FastAPI nhỏ trong `tests/`) trả stream/tool_calls theo kịch bản → test agent loop end-to-end không cần mạng thật.
- Test tuỳ chọn có cờ `--live` gọi server thật (mặc định bỏ qua trong CI).

### 7.3 Đánh giá giọng nói

- Thu **≥30–50 câu lệnh mẫu** tiếng Việt (nhiều giọng, có/không tiếng ồn, có thuật ngữ tiếng Anh) vào `tests/fixtures/audio/` kèm `expected.txt`.
- Script `scripts/eval_stt.py` tính **WER/CER** cho từng model/provider → chọn cấu hình tốt nhất cho máy bạn.
- Đo độ trễ từng chặng và in bảng: `record → VAD → STT → LLM TTFT → tool → TTS first audio`.

### 7.4 Bảng ngân sách độ trễ (mục tiêu)

| Chặng                                 | Mục tiêu                                      |
| ------------------------------------- | --------------------------------------------- |
| VAD phát hiện hết câu                 | ≤ 0.9s (theo `silence_ms`)                    |
| STT (câu ~5s)                         | ≤ 1.0–1.5s (CPU `medium` int8) / ≤ 0.5s (GPU) |
| LLM token đầu (qua ngrok)             | ≤ 2s                                          |
| TTS âm đầu tiên                       | ≤ 1.0s sau khi có câu đầu                     |
| **Tổng nói xong → bắt đầu hành động** | **≤ 3s**                                      |

### 7.5 CI

- GitHub Actions: `ruff` → `mypy` → `pytest` (matrix Linux/macOS/Windows; test audio dùng file wav, không cần thiết bị thật).

---

## 8. Rủi ro & cách giảm thiểu

| #   | Rủi ro                                             | Mức        | Giảm thiểu                                                                                                        |
| --- | -------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------- |
| 1   | STT nghe nhầm tiếng Việt → thực thi sai lệnh       | **Cao**    | Review transcript, confirm hành động, `dangerous` chỉ bằng phím, từ điển cá nhân, thử PhoWhisper/`large-v3-turbo` |
| 2   | Lệnh phá huỷ (rm, force-push…)                     | **Cao**    | Phân loại rủi ro, sandbox workdir, bắt buộc xác nhận bàn phím, audit log                                          |
| 3   | Server không hỗ trợ tool calling                   | Trung bình | `tool_mode = "prompt"` + validate JSON + retry (đã có trong Phase 1)                                              |
| 4   | Ngrok chập chờn / độ trễ cao / URL công khai       | Trung bình | Retry + backoff, timeout rõ ràng, thông báo lỗi dễ hiểu, bật xác thực cho endpoint, không commit URL/key          |
| 5   | Prompt injection (nội dung file/web chỉ đạo agent) | Trung bình | Đánh dấu tool output là _dữ liệu không đáng tin_ trong prompt; không tự động duyệt dựa trên nội dung tool output  |
| 6   | Tiếng vọng: mic nghe lại TTS                       | Trung bình | Half-duplex mặc định; barge-in chỉ khi tai nghe                                                                   |
| 7   | Độ trễ STT cao trên CPU yếu                        | Trung bình | Model nhỏ hơn + `int8`, prewarm, thử `/v1/audio/transcriptions` từ server, VAD cắt câu gọn                        |
| 8   | edge-tts (API không chính thức) ngừng hoạt động    | Thấp–TB    | Provider fallback Piper/system, cache câu cố định                                                                 |
| 9   | Khác biệt nền tảng (quyền mic, PortAudio)          | Trung bình | `claw doctor`, tài liệu từng OS, CI đa nền tảng                                                                   |
| 10  | Quyền riêng tư (âm thanh gửi đi đâu)               | Trung bình | STT chạy local mặc định; ghi rõ provider nào gửi dữ liệu ra ngoài; không lưu audio mặc định                       |
| 11  | Context phình to → chậm/đắt/lỗi                    | Thấp–TB    | Cắt output tool, nén lịch sử, đếm token                                                                           |

---

## 9. Danh sách lệnh CLI (dự kiến)

```bash
claw                         # phiên tương tác (gõ + nói)
claw ask "chạy test"         # một lượt, thoát khi xong
claw listen                  # chỉ voice: hands-free
claw --yolo                  # tắt hỏi mức write/exec (vẫn chặn dangerous)
claw --no-tts / --no-voice   # tắt giọng ra / giọng vào
claw resume [SESSION_ID]     # tiếp tục phiên cũ
claw sessions                # liệt kê phiên
claw devices                 # liệt kê mic/loa
claw doctor                  # kiểm tra mic, STT, TTS, LLM, độ trễ
claw models                  # liệt kê model từ server
claw config show|edit|path   # xem/sửa cấu hình
```

---

## 10. Backlog sau `v0.1.0`

- Streaming STT (hiển thị chữ ngay khi đang nói).
- Nhận diện người nói (chỉ phản hồi giọng chủ).
- Chạy lệnh trong container/sandbox thật (Docker, `bwrap`, `sandbox-exec`).
- Plugin tool qua entry points; marketplace "skills".
- Chế độ "pair programming": theo dõi `git diff` và nhắc bằng giọng.
- Chạy ở chế độ nền (daemon) + hotkey toàn cục.
- Cache hoá câu trả lời lặp / lệnh quen thuộc ("macro giọng nói": "deploy" = chuỗi lệnh đã định nghĩa, vẫn qua xác nhận).
- Nâng cấp UI sang Textual (tab, panel nhiều khung).

---

## 11. Câu hỏi cần chốt (để tinh chỉnh plan)

1. **Hệ điều hành & phần cứng** chính (macOS/Linux/Windows; có GPU không)? → quyết định model STT và cách xử lý audio.
2. **Server LLM** có tool calling + streaming không? Có `/v1/audio/*` không? (kết quả Phase 0 sẽ trả lời)
3. Ngôn ngữ nói: **chỉ tiếng Việt** hay xen nhiều tiếng Anh? (ảnh hưởng `initial_prompt`, model STT)
4. Phạm vi "làm việc": chỉ **coding/dev trong 1 thư mục**, hay điều khiển cả hệ thống (cài app, quản lý file toàn máy)? → ảnh hưởng mạnh tới chính sách an toàn.
5. Có cần **chạy hoàn toàn offline** về sau (LLM local) không?
6. Muốn **open-source** hay dùng nội bộ? (ảnh hưởng license, README, bảo mật mặc định)

---

## 12. Checklist tổng (theo dõi tiến độ)

- [ ] **P0** Probe server & quyết định `tool_mode`
- [ ] **P1** Agent text-only chạy được
- [ ] **P2** Tools đầy đủ + safety + audit
- [ ] **P3** Voice input (push-to-talk) — **MVP**
- [ ] **P4** Hands-free / wake-word _(tuỳ chọn)_
- [ ] **P5** Voice output (TTS) + ngắt lời
- [ ] **P6** Trải nghiệm, memory, MCP
- [ ] **P7** Hardening + phát hành `v0.1.0`

---

### Phụ lục A — `pyproject.toml` khởi đầu

```toml
[project]
name = "claw-cli"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12",
  "rich>=13.7",
  "prompt_toolkit>=3.0",
  "openai>=1.40",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "platformdirs>=4.2",
  "numpy>=1.26",
  "sounddevice>=0.4.7",
  "faster-whisper>=1.0",
  "onnxruntime>=1.18",          # cho silero-vad
  "edge-tts>=6.1",
  "structlog>=24.1",
]

[project.optional-dependencies]
wakeword = ["openwakeword>=0.6"]
piper    = ["piper-tts>=1.2"]
dev      = ["pytest", "pytest-asyncio", "respx", "ruff", "mypy", "fastapi", "uvicorn"]

[project.scripts]
claw = "claw.cli:app"
```

### Phụ lục B — Bộ câu lệnh mẫu để thử/đánh giá giọng nói

```
1.  Liệt kê các file trong thư mục này
2.  Đọc file readme rồi tóm tắt cho tôi
3.  Tìm tất cả chỗ có chữ TODO trong code
4.  Chạy test và cho biết file nào bị lỗi
5.  Cho tôi xem git status
6.  Tạo file ghi chú chấm md với nội dung họp thứ hai
7.  Đổi tên hàm get user thành fetch user trong thư mục src
8.  Cài thư viện requests rồi chạy thử script main
9.  Dung lượng thư mục này là bao nhiêu
10. Commit các thay đổi với lời nhắn sửa lỗi đăng nhập
```

> Mục tiêu: dùng bộ này (cộng thêm ~20–40 câu của riêng bạn) làm **benchmark cố định** để so sánh model STT và đo tiến bộ qua từng phiên bản.
