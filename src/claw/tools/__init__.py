"""Tools package and default registry."""

from claw.tools.ask_user import AskUserTool
from claw.tools.base import RiskLevel, Tool, ToolContext, ToolRegistry, ToolResult
from claw.tools.browser import (
    BrowserClickTool,
    BrowserGotoTool,
    BrowserPressTool,
    BrowserReadTool,
    BrowserTypeTool,
)
from claw.tools.desktop import (
    ClipboardGetTool,
    ClipboardSetTool,
    FocusWindowTool,
    GetActiveWindowTool,
    ListWindowsTool,
    NotifyTool,
    OpenAppTool,
    OpenUrlTool,
    SystemActionTool,
    WindowActionTool,
)
from claw.tools.fs import EditFileTool, GlobTool, GrepTool, ListDirTool, ReadFileTool, WriteFileTool
from claw.tools.media import MediaTool, NowPlayingTool, VolumeTool
from claw.tools.say import SayTool
from claw.tools.shell import BashTool
from claw.tools.skills import WebSearchTool, WindowLayoutTool, YoutubePlayTool
from claw.tools.ui import (
    KeyPressTool,
    TypeTextTool,
    UiClickTool,
    UiTreeTool,
    UiTypeTool,
    WaitForTool,
)
from claw.tools.vision import MouseClickTool, ScreenshotTool, ScrollTool
from claw.tools.web import WebFetchTool


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    # File & Shell
    registry.register(ListDirTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditFileTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(BashTool())
    registry.register(SayTool())
    registry.register(AskUserTool())
    registry.register(WebFetchTool())

    # Windows Computer Control (Tier 1)
    registry.register(OpenAppTool())
    registry.register(OpenUrlTool())
    registry.register(ListWindowsTool())
    registry.register(GetActiveWindowTool())
    registry.register(FocusWindowTool())
    registry.register(WindowActionTool())
    registry.register(ClipboardGetTool())
    registry.register(ClipboardSetTool())
    registry.register(NotifyTool())
    registry.register(SystemActionTool())
    registry.register(MediaTool())
    registry.register(VolumeTool())
    registry.register(NowPlayingTool())

    # High-level skills
    registry.register(YoutubePlayTool())
    registry.register(WebSearchTool())
    registry.register(WindowLayoutTool())

    # UI Automation & Input (Tier 2)
    registry.register(UiTreeTool())
    registry.register(UiClickTool())
    registry.register(UiTypeTool())
    registry.register(KeyPressTool())
    registry.register(TypeTextTool())
    registry.register(WaitForTool())

    # Browser CDP (Tier 3)
    registry.register(BrowserGotoTool())
    registry.register(BrowserClickTool())
    registry.register(BrowserTypeTool())
    registry.register(BrowserPressTool())
    registry.register(BrowserReadTool())

    # Vision & Mouse (Tier 4)
    registry.register(ScreenshotTool())
    registry.register(MouseClickTool())
    registry.register(ScrollTool())

    return registry


__all__ = [
    "AskUserTool",
    "BashTool",
    "BrowserClickTool",
    "BrowserGotoTool",
    "BrowserPressTool",
    "BrowserReadTool",
    "BrowserTypeTool",
    "ClipboardGetTool",
    "ClipboardSetTool",
    "EditFileTool",
    "FocusWindowTool",
    "GetActiveWindowTool",
    "GlobTool",
    "GrepTool",
    "KeyPressTool",
    "ListDirTool",
    "ListWindowsTool",
    "MediaTool",
    "MouseClickTool",
    "NotifyTool",
    "NowPlayingTool",
    "OpenAppTool",
    "OpenUrlTool",
    "ReadFileTool",
    "RiskLevel",
    "SayTool",
    "ScreenshotTool",
    "ScrollTool",
    "SystemActionTool",
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "TypeTextTool",
    "UiClickTool",
    "UiTreeTool",
    "UiTypeTool",
    "VolumeTool",
    "WaitForTool",
    "WebFetchTool",
    "WebSearchTool",
    "WindowActionTool",
    "WindowLayoutTool",
    "WriteFileTool",
    "YoutubePlayTool",
    "create_default_registry",
]
