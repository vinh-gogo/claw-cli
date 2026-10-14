from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gemma_stt.config_schema import GemmaSTTConfig
from gemma_stt.metrics import TranscriptionResult, summarize_metrics
from gemma_stt.model_runner import create_model_runner
from gemma_stt.output_writer import OutputWriter, clean_outputs
from gemma_stt.pipeline import NearRealtimeSTTPipeline

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gemma_stt",
        description="Gemma 4 Near-Real-Time Vietnamese Speech-to-Text (Local CUDA & Remote /v1)",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to YAML configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--backend",
        choices=["local_gemma", "remote_v1", "auto"],
        default=None,
        help="Override backend mode (local_gemma, remote_v1, or auto)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Override microphone device ID or name",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Optional run duration in seconds (0 = run until Ctrl+C)",
    )
    parser.add_argument(
        "--clean-outputs",
        action="store_true",
        help="Delete existing transcript, JSONL, metrics CSV, and debug WAV files and exit",
    )
    parser.add_argument(
        "--forward-claw",
        action="store_true",
        help="Forward each recognized Vietnamese utterance to ClawApp (Gemma 4 26B on Colab /v1)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    console = Console()

    cfg = GemmaSTTConfig.load(args.config)
    if args.backend:
        cfg.backend.mode = args.backend  # type: ignore[assignment]
    if args.device is not None:
        cfg.audio.device = args.device

    if args.clean_outputs:
        removed = clean_outputs(cfg.output)
        console.print(f"[green]Đã xóa {len(removed)} đường dẫn dữ liệu đầu ra:[/green] {removed}")
        return 0

    claw_app: Any = None
    if args.forward_claw:
        from claw.app import ClawApp

        claw_app = ClawApp()

    console.print(
        Panel.fit(
            f"[bold cyan]Gemma 4 Vietnamese Near-Real-Time STT[/bold cyan]\n"
            f"Backend: [yellow]{cfg.backend.mode}[/yellow] · Model: [green]{cfg.model.id}[/green]\n"
            f"VAD: [magenta]{cfg.vad.engine}[/magenta] (silence={cfg.vad.silence_ms}ms, max={cfg.vad.max_segment_ms}ms) · "
            f"Queue Policy: [cyan]{cfg.queue.policy}[/cyan]",
            border_style="cyan",
        )
    )

    try:
        runner = create_model_runner(cfg)
    except Exception as exc:
        console.print(f"[bold red]Lỗi khởi tạo Model Runner:[/bold red] {exc}")
        return 1

    def render_result(res: TranscriptionResult) -> None:
        if res.dropped:
            console.print(
                f"[bold red][#{res.segment_id:03d} DROPPED][/bold red] "
                f"Quá tải hàng đợi (wait={res.queue_wait_s:.2f}s, dur={res.duration_s:.2f}s)"
            )
            return
        if not res.text:
            console.print(
                f"[dim][#{res.segment_id:03d}] (im lặng / không có giọng nói) "
                f"[dur={res.duration_s:.2f}s, inf={res.inference_s:.2f}s][/dim]"
            )
            return

        console.print(
            f"[bold green][#{res.segment_id:03d}][/bold green] {res.text} "
            f"[dim](dur={res.duration_s:.2f}s | inf={res.inference_s:.2f}s | "
            f"wait={res.queue_wait_s:.2f}s | E2E={res.e2e_voice_end_s:.2f}s | RTF={res.rtf:.2f})[/dim]"
        )
        if claw_app is not None:
            console.print("[cyan]↳ Chuyển lệnh sang Claw Agent (Colab /v1)...[/cyan]")
            try:
                asyncio.run(claw_app.run_turn(res.text))
            except Exception as agent_err:
                console.print(f"[red]Lỗi Claw Agent: {agent_err}[/red]")

    writer = OutputWriter(cfg.output, console_callback=render_result)
    pipeline = NearRealtimeSTTPipeline(cfg=cfg, model_runner=runner, output_writer=writer)

    stop_requested = False

    def handle_sigint(signum: int, frame: Any) -> None:
        nonlocal stop_requested
        if not stop_requested:
            stop_requested = True
            console.print(
                "\n[yellow]Đang dừng thu âm và xử lý nốt các đoạn trong hàng đợi (nhấn Ctrl+C lần nữa để hủy ngay)...[/yellow]"
            )
        else:
            console.print("\n[red]Hủy khẩn cấp các đoạn đang chờ![/red]")
            pipeline.stop(drain=False, timeout=2.0)
            sys.exit(130)

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        pipeline.start()
        console.print("[bold green]🎙 Đang nghe từ microphone... (Nhấn Ctrl+C để dừng)[/bold green]")
        start_time = time.monotonic()
        while not stop_requested:
            if not pipeline.capture.is_running:
                err = pipeline.capture.stream_error or "Microphone stream stopped."
                console.print(f"[bold red]Lỗi thiết bị thu âm:[/bold red] {err}")
                break
            if args.duration > 0 and (time.monotonic() - start_time) >= args.duration:
                console.print(f"[yellow]Đã đạt thời lượng chạy {args.duration:.1f}s.[/yellow]")
                break
            time.sleep(0.1)
    finally:
        pipeline.stop(drain=True)

    summary = summarize_metrics(writer.history)
    table = Table(title="Tổng kết Phiên Nhận Dạng (Session Metrics)")
    table.add_column("Chỉ số", style="cyan")
    table.add_column("Giá trị", style="green")
    for k, v in summary.items():
        table.add_row(str(k), str(v))
    console.print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
