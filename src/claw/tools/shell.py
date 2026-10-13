from __future__ import annotations

import asyncio
import os
import subprocess
import sys

from pydantic import BaseModel, Field

from claw.tools.base import RiskLevel, Tool, ToolContext, ToolResult


class BashArgs(BaseModel):
    cmd: str = Field(description="Lệnh shell cần thực thi")
    timeout: int = Field(default=60, ge=1, le=600, description="Thời gian chờ tối đa tính bằng giây")


class BashTool(Tool):
    name = "bash"
    description = "Chạy một lệnh shell trong thư mục làm việc hiện tại."
    risk: RiskLevel = "exec"
    args_model = BashArgs

    async def run(self, args: BashArgs, ctx: ToolContext) -> ToolResult:
        if ctx.cancel_event.is_set():
            return ToolResult.fail("Hành động đã bị huỷ trước khi bắt đầu.")

        clean_env = ctx.scrubbed_env()
        # Set PYTHONIOENCODING=utf-8
        clean_env["PYTHONIOENCODING"] = "utf-8"

        # Choose shell command based on OS
        is_win = sys.platform == "win32"
        shell_cmd = args.cmd

        try:
            # We run the command through the default shell
            proc = await asyncio.create_subprocess_shell(
                shell_cmd,
                cwd=str(ctx.workdir),
                env=clean_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if is_win else 0,
            )
        except Exception as e:
            return ToolResult.fail(f"Không thể khởi động tiến trình shell: {e}")

        async def wait_process() -> tuple[bytes, int]:
            stdout_bytes, _ = await proc.communicate()
            return stdout_bytes, proc.returncode or 0

        async def wait_cancel() -> None:
            await ctx.cancel_event.wait()
            self._kill_process(proc.pid, is_win)

        cancel_task = asyncio.create_task(wait_cancel())
        timed_out = False
        try:
            stdout_bytes, code = await asyncio.wait_for(wait_process(), timeout=float(args.timeout))
        except asyncio.TimeoutError:
            timed_out = True
            self._kill_process(proc.pid, is_win)
            try:
                stdout_bytes, _ = await proc.communicate()
            except Exception:
                stdout_bytes = b""
            code = -1
        except asyncio.CancelledError:
            self._kill_process(proc.pid, is_win)
            raise
        finally:
            cancel_task.cancel()

        output_str = stdout_bytes.decode("utf-8", errors="replace").strip()

        # Handle output truncation
        if len(output_str) > ctx.max_output_chars:
            cut_count = len(output_str) - ctx.max_output_chars
            output_str = output_str[: ctx.max_output_chars] + f"\n... [Đã cắt bớt {cut_count:,} ký tự]"

        if timed_out:
            return ToolResult.fail(
                f"Lệnh bị timeout sau {args.timeout} giây.",
                output=output_str,
            )

        if ctx.cancel_event.is_set():
            return ToolResult.fail("Lệnh đã bị huỷ bởi người dùng.", output=output_str)

        if code != 0:
            return ToolResult(
                output=output_str,
                error=f"Lệnh kết thúc với mã lỗi {code}",
                is_error=True,
            )

        return ToolResult.success(output_str if output_str else "(Lệnh đã chạy thành công không có output)")

    def _kill_process(self, pid: int | None, is_win: bool) -> None:
        if pid is None:
            return
        try:
            if is_win:
                # Force kill process tree on Windows
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                import signal

                killpg = getattr(os, "killpg", None)
                getpgid = getattr(os, "getpgid", None)
                sigkill = getattr(signal, "SIGKILL", getattr(signal, "SIGTERM", 15))
                if killpg and getpgid:
                    killpg(getpgid(pid), sigkill)
                else:
                    os.kill(pid, sigkill)
        except Exception:
            pass
