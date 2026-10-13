from __future__ import annotations

from pathlib import Path

import pytest

from claw.events import SayEvent
from claw.tools.base import ToolContext
from claw.tools.fs import (
    EditFileArgs,
    EditFileTool,
    GlobArgs,
    GlobTool,
    GrepArgs,
    GrepTool,
    ListDirArgs,
    ListDirTool,
    ReadFileArgs,
    ReadFileTool,
    WriteFileArgs,
    WriteFileTool,
)
from claw.tools.say import SayArgs, SayTool
from claw.tools.shell import BashArgs, BashTool


@pytest.mark.asyncio
async def test_fs_tools_crud(tmp_path: Path) -> None:
    ctx = ToolContext(workdir=tmp_path)

    # 1. Write file
    write_tool = WriteFileTool()
    res = await write_tool.run(WriteFileArgs(path="test.txt", content="line 1\nline 2\nline 3\n"), ctx)
    assert not res.is_error
    assert (tmp_path / "test.txt").is_file()

    # 2. Read file
    read_tool = ReadFileTool()
    res = await read_tool.run(ReadFileArgs(path="test.txt", offset=1, limit=2), ctx)
    assert not res.is_error
    assert "line 1" in res.output
    assert "line 2" in res.output

    # 3. Edit file (success)
    edit_tool = EditFileTool()
    res = await edit_tool.run(EditFileArgs(path="test.txt", old="line 2", new="line TWO"), ctx)
    assert not res.is_error
    assert "line TWO" in (tmp_path / "test.txt").read_text(encoding="utf-8")

    # 4. Edit file (ambiguous multiple occurrences error)
    (tmp_path / "dup.txt").write_text("foo bar foo", encoding="utf-8")
    res = await edit_tool.run(EditFileArgs(path="dup.txt", old="foo", new="baz"), ctx)
    assert res.is_error
    assert "xuất hiện 2 lần" in res.error

    # 5. Edit file (not found error)
    res = await edit_tool.run(EditFileArgs(path="dup.txt", old="missing", new="baz"), ctx)
    assert res.is_error
    assert "Không tìm thấy" in res.error

    # 6. List dir
    list_tool = ListDirTool()
    res = await list_tool.run(ListDirArgs(path="."), ctx)
    assert not res.is_error
    assert "test.txt" in res.output
    assert "dup.txt" in res.output

    # 7. Glob
    glob_tool = GlobTool()
    res = await glob_tool.run(GlobArgs(pattern="*.txt"), ctx)
    assert not res.is_error
    assert "test.txt" in res.output

    # 8. Grep
    grep_tool = GrepTool()
    res = await grep_tool.run(GrepArgs(pattern="line TWO"), ctx)
    assert not res.is_error
    assert "test.txt" in res.output


@pytest.mark.asyncio
async def test_read_binary_file(tmp_path: Path) -> None:
    ctx = ToolContext(workdir=tmp_path)
    bin_file = tmp_path / "test.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03\x04")

    read_tool = ReadFileTool()
    res = await read_tool.run(ReadFileArgs(path="test.bin"), ctx)
    assert res.is_error
    assert "nhị phân" in res.error


@pytest.mark.asyncio
async def test_bash_tool(tmp_path: Path) -> None:
    ctx = ToolContext(workdir=tmp_path)
    bash = BashTool()

    # Simple echo
    res = await bash.run(BashArgs(cmd="echo hello_claw"), ctx)
    assert not res.is_error
    assert "hello_claw" in res.output

    # Non-zero exit code
    res = await bash.run(BashArgs(cmd="exit 42"), ctx)
    assert res.is_error
    assert "42" in res.error

    # Output truncation
    ctx_small = ToolContext(workdir=tmp_path, max_output_chars=50)
    res = await bash.run(BashArgs(cmd="python -c \"print('A' * 200)\""), ctx_small)
    assert not res.is_error
    assert "Đã cắt bớt" in res.output


@pytest.mark.asyncio
async def test_say_tool() -> None:
    events = []

    async def mock_emit(evt):
        events.append(evt)

    ctx = ToolContext(emit_event=mock_emit)
    say_tool = SayTool()
    res = await say_tool.run(SayArgs(text="Xin chào Việt Nam"), ctx)

    assert not res.is_error
    assert len(events) == 1
    assert isinstance(events[0], SayEvent)
    assert events[0].text == "Xin chào Việt Nam"
