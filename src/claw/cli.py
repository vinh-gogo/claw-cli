from __future__ import annotations

import sys

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import time
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from claw.app import ClawApp
from claw.config import Config, get_config, set_config
from claw.session.store import SessionStore
from claw.voice.devices import list_audio_devices

app = typer.Typer(
    name="claw",
    help="Trợ lý dòng lệnh thông minh điều khiển bằng giọng nói và máy tính Windows tiếng Việt.",
    add_completion=False,
)
console = Console(legacy_windows=False)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    no_tts: bool = typer.Option(False, "--no-tts", help="Tắt phản hồi giọng nói (TTS)"),
    no_voice: bool = typer.Option(False, "--no-voice", help="Tắt thu âm microphone"),
    yolo: bool = typer.Option(False, "--yolo", help="Tự động duyệt các lệnh write/exec thông thường"),
    control: Optional[str] = typer.Option(None, "--control", help="Chế độ điều khiển máy: ask | allowlist | free"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Tên model LLM chỉ định"),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Base URL cho LLM server"),
) -> None:
    """Khởi động claw CLI."""
    if ctx.invoked_subcommand is not None:
        return

    cfg = get_config()
    if no_tts:
        cfg.tts.speak_mode = "off"
    if yolo:
        cfg.safety.yolo = True
    if control and control in ("ask", "allowlist", "free"):
        cfg.desktop.control_mode = control  # type: ignore[assignment]
    if model:
        cfg.llm.model = model
    if base_url:
        cfg.llm.base_url = base_url
    set_config(cfg)

    claw_app = ClawApp(cfg)
    asyncio.run(claw_app.run_interactive())


@app.command("ask")
def ask(
    prompt: str = typer.Argument(..., help="Nội dung yêu cầu hoặc câu hỏi cho claw"),
    yolo: bool = typer.Option(False, "--yolo", help="Tự động duyệt lệnh"),
    control: Optional[str] = typer.Option(None, "--control", help="Chế độ điều khiển máy: ask | allowlist | free"),
    no_tts: bool = typer.Option(True, "--tts/--no-tts", help="Bật/tắt đọc kết quả to"),
) -> None:
    """Thực thi một yêu cầu duy nhất rồi thoát."""
    cfg = get_config()
    if not no_tts:
        cfg.tts.speak_mode = "summary"
    else:
        cfg.tts.speak_mode = "off"
    if yolo:
        cfg.safety.yolo = True
    if control and control in ("ask", "allowlist", "free"):
        cfg.desktop.control_mode = control  # type: ignore[assignment]
    set_config(cfg)

    claw_app = ClawApp(cfg)
    asyncio.run(claw_app.run_turn(prompt))


@app.command("listen")
def listen(
    yolo: bool = typer.Option(False, "--yolo", help="Tự động duyệt lệnh"),
    control: Optional[str] = typer.Option(None, "--control", help="Chế độ điều khiển máy: ask | allowlist | free"),
) -> None:
    """Chế độ lắng nghe giọng nói trực tiếp."""
    cfg = get_config()
    if yolo:
        cfg.safety.yolo = True
    if control and control in ("ask", "allowlist", "free"):
        cfg.desktop.control_mode = control  # type: ignore[assignment]
    set_config(cfg)

    claw_app = ClawApp(cfg)

    async def _listen_loop() -> None:
        console.print("[bold cyan]Bắt đầu lắng nghe... Hãy nói yêu cầu của bạn vào mic.[/bold cyan]")
        spoken = await claw_app.record_voice_input()
        if spoken:
            console.print(f"🎙 [bold green]\"{spoken}\"[/bold green]")
            await claw_app.run_turn(spoken)

    asyncio.run(_listen_loop())


@app.command("apps")
def apps_cmd() -> None:
    """Liệt kê danh sách các ứng dụng tìm thấy trên Windows và alias tiếng Việt."""
    from claw.winctl.apps import AppManager

    mgr = AppManager()
    app_list = mgr.list_apps()
    table = Table(title=f"Danh sách ứng dụng và Alias tiếng Việt ({len(app_list)} apps)", border_style="cyan")
    table.add_column("Mã App (ID)", style="bold cyan")
    table.add_column("Alias tiếng Việt", style="green")
    table.add_column("Đích thực thi / Đường dẫn", style="dim")

    for item in app_list:
        aliases = ", ".join(item.get("aliases", []))
        table.add_row(item["app_id"], aliases, str(item["target"]))

    console.print(table)


@app.command("skills")
def skills_cmd() -> None:
    """Liệt kê các kỹ năng / macro cấp cao có sẵn trong claw."""
    table = Table(title="Danh sách Kỹ năng (Skills / Macros) của claw", border_style="magenta")
    table.add_column("Tên Skill", style="bold magenta")
    table.add_column("Mức rủi ro", style="green")
    table.add_column("Mô tả")

    table.add_row("youtube_play", "low", "Tìm kiếm và tự động phát nhạc/video trên YouTube bằng trình duyệt")
    table.add_row("web_search", "low", "Tìm kiếm thông tin trên Google, Bing, Cốc Cốc, DuckDuckGo...")
    table.add_row("window_layout", "low", "Sắp xếp chia đôi màn hình 2 cửa sổ (một bên trái, một bên phải)")

    console.print(table)


@app.command("inspect")
def inspect_cmd(
    window: Optional[str] = typer.Option(None, "--window", "-w", help="Tiêu đề hoặc hwnd của cửa sổ cần đọc cây UI"),
    depth: int = typer.Option(4, "--depth", "-d", help="Độ sâu tối đa của cây UI"),
) -> None:
    """Dump cây UI Automation rút gọn của một cửa sổ ứng dụng để kiểm tra selector."""
    from claw.winctl.uia import dump_ui_tree
    from claw.winctl.windows import find_window

    hwnd = None
    if window:
        w = find_window(window)
        if not w:
            console.print(f"[red]Không tìm thấy cửa sổ nào khớp với '{window}'[/red]")
            return
        hwnd = w["hwnd"]

    text_tree, _ = dump_ui_tree(hwnd=hwnd, max_depth=depth)
    console.print(text_tree)


@app.command("devices")
def devices() -> None:
    """Liệt kê danh sách microphone và loa có sẵn trên hệ thống."""
    dev_dict = list_audio_devices()
    if "error" in dev_dict and dev_dict["error"]:
        console.print(f"[red]Lỗi khi truy vấn thiết bị âm thanh:[/red] {dev_dict['error']}")
        return

    table_in = Table(title="Microphones (Đầu vào)", border_style="cyan")
    table_in.add_column("Index", style="dim", justify="right")
    table_in.add_column("Tên thiết bị")
    table_in.add_column("Kênh", justify="right")
    table_in.add_column("Mặc định")

    for d in dev_dict.get("inputs", []):
        is_def = "[bold green]✔[/bold green]" if d.get("is_default") else ""
        table_in.add_row(str(d["index"]), d["name"], str(d["max_input_channels"]), is_def)

    table_out = Table(title="Loa / Tai nghe (Đầu ra)", border_style="green")
    table_out.add_column("Index", style="dim", justify="right")
    table_out.add_column("Tên thiết bị")
    table_out.add_column("Kênh", justify="right")
    table_out.add_column("Mặc định")

    for d in dev_dict.get("outputs", []):
        is_def = "[bold green]✔[/bold green]" if d.get("is_default") else ""
        table_out.add_row(str(d["index"]), d["name"], str(d["max_output_channels"]), is_def)

    console.print(table_in)
    console.print()
    console.print(table_out)


@app.command("sessions")
def sessions() -> None:
    """Liệt kê lịch sử các phiên làm việc đã lưu."""
    cfg = get_config()
    store = SessionStore(cfg.session.dir)
    session_list = store.list_sessions()

    if not session_list:
        console.print("[dim]Chưa có phiên làm việc nào được lưu.[/dim]")
        return

    table = Table(title=f"Danh sách phiên làm việc ({cfg.session.dir})", border_style="blue")
    table.add_column("Mã phiên (Session ID)", style="cyan")
    table.add_column("Thời gian sửa", style="dim")
    table.add_column("Kích thước", justify="right")

    for s in session_list:
        table.add_row(s["session_id"], s["modified"], f"{s['size_bytes']:,} B")

    console.print(table)


@app.command("resume")
def resume(
    session_id: str = typer.Argument(..., help="Mã phiên (hoặc phần đầu của mã) cần tiếp tục"),
) -> None:
    """Tiếp tục một phiên làm việc cũ."""
    cfg = get_config()
    claw_app = ClawApp(cfg)
    try:
        loaded_messages = claw_app.session_store.load_session(session_id)
        claw_app.context.messages = loaded_messages
        claw_app.current_session_id = session_id
        console.print(f"[bold green]Đã nạp lại phiên {session_id} ({len(loaded_messages)} tin nhắn).[/bold green]")
        asyncio.run(claw_app.run_interactive())
    except Exception as e:
        console.print(f"[bold red]Lỗi khi nạp phiên:[/bold red] {e}")


@app.command("models")
def models() -> None:
    """Liệt kê các model khả dụng từ LLM server."""
    cfg = get_config()
    claw_app = ClawApp(cfg)

    async def _fetch():
        try:
            m_list = await claw_app.llm.client.models.list()
            console.print(f"[bold green]Các model tại {cfg.llm.base_url}:[/bold green]")
            for m in m_list.data:
                console.print(f"- {m.id}")
        except Exception as e:
            console.print(f"[bold red]Không thể lấy danh sách model:[/bold red] {e}")

    asyncio.run(_fetch())


@app.command("doctor")
def doctor() -> None:
    """Chẩn đoán kiểm tra toàn diện: Mic, Loa, STT, TTS, LLM Server, Windows Control."""
    console.print(Panel.fit("[bold cyan]CLAW DOCTOR — Kiểm tra hệ thống[/bold cyan]", border_style="cyan"))

    cfg = get_config()

    # 1. Check Python & Audio Devices
    console.print(f"1. Python: [bold]{sys.version.split()[0]}[/bold] ({sys.platform})")
    devs = list_audio_devices()
    num_in = len(devs.get("inputs", []))
    num_out = len(devs.get("outputs", []))
    if num_in > 0:
        console.print(f"   - Mic: [bold green]✔[/bold green] Tìm thấy {num_in} thiết bị ghi âm")
    else:
        console.print("   - Mic: [bold red]✘[/bold red] Không tìm thấy microphone nào")

    if num_out > 0:
        console.print(f"   - Loa: [bold green]✔[/bold green] Tìm thấy {num_out} thiết bị phát âm")
    else:
        console.print("   - Loa: [bold red]✘[/bold red] Không tìm thấy loa nào")

    # 2. Check STT
    console.print(f"2. STT Provider: [bold]{cfg.stt.provider}[/bold] (model: {cfg.stt.model})")
    import importlib.util

    if cfg.stt.provider == "gemma-stt":
        console.print(
            f"   - gemma-stt: [bold green]✔[/bold green] Đã kích hoạt (Colab /v1: {cfg.llm.base_url})"
        )
    elif importlib.util.find_spec("faster_whisper") is not None:
        console.print("   - faster-whisper: [bold green]✔[/bold green] Đã cài đặt")
    else:
        console.print("   - faster-whisper: [bold red]✘[/bold red] Chưa cài đặt")

    # 3. Check TTS
    console.print(f"3. TTS Provider: [bold]{cfg.tts.provider}[/bold] (voice: {cfg.tts.voice})")
    if importlib.util.find_spec("edge_tts") is not None:
        console.print("   - edge-tts: [bold green]✔[/bold green] Đã cài đặt")
    else:
        console.print("   - edge-tts: [bold red]✘[/bold red] Chưa cài đặt")

    # 4. Check Windows Computer Control Packages
    console.print("4. Windows Computer Control:")
    for pkg in ("win32gui", "pywinauto", "pycaw", "yt_dlp", "mss", "PIL", "keyboard", "playwright"):
        spec = importlib.util.find_spec(pkg)
        if spec is not None:
            console.print(f"   - {pkg}: [bold green]✔[/bold green] OK")
        else:
            console.print(f"   - {pkg}: [bold yellow]✘ Chưa cài đặt[/bold yellow]")

    # 5. Check LLM Server
    masked_url = cfg.llm.base_url
    console.print(f"5. LLM Server: [bold]{masked_url}[/bold]")

    async def _test_llm():
        claw_app = ClawApp(cfg)
        t0 = time.perf_counter()
        try:
            m = await claw_app.llm.get_model()
            latency = (time.perf_counter() - t0) * 1000
            console.print(f"   - Kết nối: [bold green]✔[/bold green] OK ({latency:.1f}ms, model: {m})")
        except Exception as e:
            console.print(f"   - Kết nối: [bold red]✘ Thất bại[/bold red] ({e})")

    asyncio.run(_test_llm())


@app.command("config")
def config_cmd(
    action: str = typer.Argument("show", help="Thao tác: show | path"),
) -> None:
    """Xem thông tin cấu hình."""
    cfg = get_config()
    cfg_path = Config.find_config_file()

    if action == "path":
        console.print(str(cfg_path) if cfg_path else "Chưa có tệp config.toml nào.")
    else:
        console.print(f"[dim]Tệp cấu hình:[/dim] {cfg_path or 'Mặc định (Environment / Built-in)'}\n")
        console.print(cfg.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
