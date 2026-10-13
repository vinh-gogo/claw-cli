from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from claw.tools.base import Tool, ToolContext, ToolResult
from claw.winctl.media import get_now_playing, press_media_key
from claw.winctl.volume import change_volume, get_volume, is_muted, set_mute, set_volume

logger = logging.getLogger("claw.tools.media")


class MediaArgs(BaseModel):
    action: Literal["play_pause", "play", "pause", "next", "prev", "stop"] = Field(
        ..., description="Hành động đa phương tiện: play_pause, next, prev, stop"
    )


class MediaTool(Tool):
    name = "media"
    description = "Điều khiển phát nhạc/video trên Windows: tạm dừng/phát tiếp (play_pause), bài tiếp (next), bài trước (prev), dừng hẳn (stop)."
    risk = "low"
    args_model = MediaArgs

    async def run(self, args: MediaArgs, ctx: ToolContext) -> ToolResult:
        ok, msg = press_media_key(args.action)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class VolumeArgs(BaseModel):
    action: Literal["get", "set", "up", "down", "mute", "unmute"] = Field(
        ..., description="Thao tác: get (đọc), set (đặt mức 0-100), up (tăng), down (giảm), mute (tắt tiếng), unmute (bật tiếng)"
    )
    value: int | None = Field(default=None, description="Giá trị phần trăm (0-100) khi dùng action='set' hoặc số phần trăm tăng/giảm")


class VolumeTool(Tool):
    name = "volume"
    description = "Điều chỉnh hoặc kiểm tra âm lượng loa hệ thống Windows."
    risk = "low"
    args_model = VolumeArgs

    async def run(self, args: VolumeArgs, ctx: ToolContext) -> ToolResult:
        act = args.action
        if act == "get":
            vol = get_volume()
            muted = is_muted()
            state = " (đang tắt tiếng)" if muted else ""
            return ToolResult.success(f"Âm lượng hiện tại: {vol}%{state}")

        if act == "set":
            target = args.value if args.value is not None else 50
            ok, final_vol = set_volume(target)
            return ToolResult.success(f"Đã đặt âm lượng thành {final_vol}%")

        if act == "up":
            delta = args.value if args.value is not None else 10
            ok, final_vol = change_volume(abs(delta))
            return ToolResult.success(f"Đã tăng âm lượng lên {final_vol}% (+{delta}%)")

        if act == "down":
            delta = args.value if args.value is not None else 10
            ok, final_vol = change_volume(-abs(delta))
            return ToolResult.success(f"Đã giảm âm lượng xuống {final_vol}% (-{delta}%)")

        if act == "mute":
            set_mute(True)
            return ToolResult.success("Đã tắt tiếng âm lượng hệ thống.")

        if act == "unmute":
            set_mute(False)
            return ToolResult.success(f"Đã bật lại tiếng (âm lượng: {get_volume()}%).")

        return ToolResult.fail(f"Hành động '{act}' không hợp lệ.")


class EmptyArgs(BaseModel):
    pass


class NowPlayingTool(Tool):
    name = "now_playing"
    description = "Kiểm tra bài hát hoặc video đang phát trên hệ thống (tiêu đề, nghệ sĩ, ứng dụng nguồn, trạng thái phát)."
    risk = "read"
    args_model = EmptyArgs

    async def run(self, args: EmptyArgs, ctx: ToolContext) -> ToolResult:
        info = await get_now_playing()
        title = info.get("title")
        status = info.get("status")
        artist = info.get("artist")
        source = info.get("source")

        if not title:
            return ToolResult.success("Hiện không phát hiện thấy media nào đang phát.")

        msg = f"Đang phát: \"{title}\""
        if artist:
            msg += f" - {artist}"
        if source:
            msg += f" (Nguồn: {source})"
        msg += f" [Trạng thái: {status}]"

        return ToolResult.success(msg)
