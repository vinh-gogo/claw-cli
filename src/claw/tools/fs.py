from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from claw.safety.sandbox import PathSandbox
from claw.tools.base import RiskLevel, Tool, ToolContext, ToolResult


def is_binary_file(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            return b"\0" in chunk
    except Exception:
        return False


# --- list_dir Tool ---
class ListDirArgs(BaseModel):
    path: str = Field(default=".", description="Đường dẫn thư mục cần xem")


class ListDirTool(Tool):
    name = "list_dir"
    description = "Liệt kê danh sách tệp tin và thư mục con trong đường dẫn chỉ định."
    risk: RiskLevel = "read"
    args_model = ListDirArgs

    async def run(self, args: ListDirArgs, ctx: ToolContext) -> ToolResult:
        sandbox = PathSandbox(ctx.workdir)
        try:
            target = sandbox.resolve_safe(args.path)
        except Exception as e:
            return ToolResult.fail(str(e))

        if not target.is_dir():
            return ToolResult.fail(f"'{args.path}' không phải là thư mục hợp lệ.")

        items: list[str] = []
        try:
            for entry in sorted(target.iterdir()):
                rel = entry.relative_to(ctx.workdir)
                if entry.is_dir():
                    items.append(f"📁 {rel}/")
                else:
                    size = entry.stat().st_size
                    items.append(f"📄 {rel} ({size:,} bytes)")
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi đọc thư mục: {e}")

        output = f"Nội dung trong '{args.path}':\n" + "\n".join(items) if items else f"Thư mục '{args.path}' trống."
        return ToolResult.success(output)


# --- read_file Tool ---
class ReadFileArgs(BaseModel):
    path: str = Field(description="Đường dẫn tệp tin cần đọc")
    offset: int = Field(default=1, ge=1, description="Dòng bắt đầu đọc (1-indexed)")
    limit: int = Field(default=200, ge=1, le=1000, description="Số lượng dòng tối đa cần đọc")


class ReadFileTool(Tool):
    name = "read_file"
    description = "Đọc nội dung của một tệp văn bản theo phạm vi dòng chỉ định."
    risk: RiskLevel = "read"
    args_model = ReadFileArgs

    async def run(self, args: ReadFileArgs, ctx: ToolContext) -> ToolResult:
        sandbox = PathSandbox(ctx.workdir)
        try:
            target = sandbox.resolve_safe(args.path)
        except Exception as e:
            return ToolResult.fail(str(e))

        if not target.is_file():
            return ToolResult.fail(f"Tệp '{args.path}' không tồn tại.")

        if is_binary_file(target):
            return ToolResult.fail(f"Tệp '{args.path}' là tệp nhị phân (binary), không thể đọc dưới dạng văn bản.")

        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi đọc tệp '{args.path}': {e}")

        total_lines = len(lines)
        start_idx = args.offset - 1
        end_idx = min(start_idx + args.limit, total_lines)

        selected = lines[start_idx:end_idx]
        formatted: list[str] = []
        for i, line in enumerate(selected, start=args.offset):
            formatted.append(f"{i:4d}: {line}")

        header = f"Tệp: {args.path} (Dòng {args.offset}–{end_idx} / Tổng {total_lines} dòng)\n"
        return ToolResult.success(header + "\n".join(formatted))


# --- write_file Tool ---
class WriteFileArgs(BaseModel):
    path: str = Field(description="Đường dẫn tệp tin cần ghi")
    content: str = Field(description="Nội dung cần ghi vào tệp")


class WriteFileTool(Tool):
    name = "write_file"
    description = "Tạo mới hoặc ghi đè toàn bộ nội dung của tệp tin."
    risk: RiskLevel = "write"
    args_model = WriteFileArgs

    async def run(self, args: WriteFileArgs, ctx: ToolContext) -> ToolResult:
        sandbox = PathSandbox(ctx.workdir)
        try:
            target = sandbox.resolve_safe(args.path)
        except Exception as e:
            return ToolResult.fail(str(e))

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args.content, encoding="utf-8")
            return ToolResult.success(f"Đã ghi thành công {len(args.content)} ký tự vào '{args.path}'.")
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi ghi tệp: {e}")


# --- edit_file Tool ---
class EditFileArgs(BaseModel):
    path: str = Field(description="Đường dẫn tệp tin cần sửa")
    old: str = Field(description="Đoạn văn bản gốc cần thay thế (phải là duy nhất)")
    new: str = Field(description="Đoạn văn bản mới thay thế vào")


class EditFileTool(Tool):
    name = "edit_file"
    description = "Thay thế chính xác một đoạn văn bản trong tệp. Báo lỗi nếu đoạn cũ xuất hiện nhiều lần hoặc không tìm thấy."
    risk: RiskLevel = "write"
    args_model = EditFileArgs

    async def run(self, args: EditFileArgs, ctx: ToolContext) -> ToolResult:
        sandbox = PathSandbox(ctx.workdir)
        try:
            target = sandbox.resolve_safe(args.path)
        except Exception as e:
            return ToolResult.fail(str(e))

        if not target.is_file():
            return ToolResult.fail(f"Tệp '{args.path}' không tồn tại.")

        try:
            content = target.read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi đọc tệp '{args.path}': {e}")

        occurrences = content.count(args.old)
        if occurrences == 0:
            return ToolResult.fail(f"Không tìm thấy đoạn văn bản cần thay thế trong '{args.path}'.")
        if occurrences > 1:
            return ToolResult.fail(
                f"Đoạn văn bản cần thay thế xuất hiện {occurrences} lần trong '{args.path}'. Hãy cung cấp thêm ngữ cảnh xung quanh để xác định duy nhất."
            )

        new_content = content.replace(args.old, args.new, 1)
        try:
            target.write_text(new_content, encoding="utf-8")
            return ToolResult.success(f"Đã cập nhật thành công tệp '{args.path}'.")
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi lưu tệp '{args.path}': {e}")


# --- glob Tool ---
class GlobArgs(BaseModel):
    pattern: str = Field(description="Mẫu tìm kiếm tệp (ví dụ: '**/*.py', 'src/**/*.rs')")
    path: str = Field(default=".", description="Thư mục gốc bắt đầu tìm")


class GlobTool(Tool):
    name = "glob"
    description = "Tìm kiếm danh sách tệp tin khớp với biểu thức glob pattern."
    risk: RiskLevel = "read"
    args_model = GlobArgs

    async def run(self, args: GlobArgs, ctx: ToolContext) -> ToolResult:
        sandbox = PathSandbox(ctx.workdir)
        try:
            base = sandbox.resolve_safe(args.path)
        except Exception as e:
            return ToolResult.fail(str(e))

        ignore_dirs = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
        matches: list[str] = []

        try:
            for root, dirs, files in os.walk(base):
                # prune ignored directories in-place
                dirs[:] = [d for d in dirs if d not in ignore_dirs]
                for file in files:
                    full_p = Path(root) / file
                    rel_p = str(full_p.relative_to(ctx.workdir)).replace("\\", "/")
                    if fnmatch.fnmatch(rel_p, args.pattern) or fnmatch.fnmatch(file, args.pattern):
                        matches.append(rel_p)
                        if len(matches) >= 500:
                            break
                if len(matches) >= 500:
                    break
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi thực hiện glob: {e}")

        if not matches:
            return ToolResult.success(f"Không tìm thấy tệp nào khớp với '{args.pattern}'.")

        res_str = f"Tìm thấy {len(matches)} tệp khớp với '{args.pattern}':\n" + "\n".join(matches[:100])
        if len(matches) > 100:
            res_str += f"\n... [và {len(matches) - 100} tệp khác]"
        return ToolResult.success(res_str)


# --- grep Tool ---
class GrepArgs(BaseModel):
    pattern: str = Field(description="Chuỗi hoặc regex cần tìm kiếm trong nội dung các tệp")
    path: str = Field(default=".", description="Thư mục hoặc tệp cần tìm kiếm")


class GrepTool(Tool):
    name = "grep"
    description = "Tìm kiếm chuỗi hoặc biểu thức regex trong nội dung các tệp tin văn bản."
    risk: RiskLevel = "read"
    args_model = GrepArgs

    async def run(self, args: GrepArgs, ctx: ToolContext) -> ToolResult:
        sandbox = PathSandbox(ctx.workdir)
        try:
            base = sandbox.resolve_safe(args.path)
        except Exception as e:
            return ToolResult.fail(str(e))

        try:
            compiled_re = re.compile(args.pattern, re.IGNORECASE)
        except Exception as e:
            return ToolResult.fail(f"Biểu thức regex không hợp lệ '{args.pattern}': {e}")

        ignore_dirs = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
        results: list[str] = []

        target_files: list[Path] = []
        if base.is_file():
            target_files.append(base)
        else:
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in ignore_dirs]
                for f in files:
                    p = Path(root) / f
                    if not is_binary_file(p):
                        target_files.append(p)
                    if len(target_files) >= 1000:
                        break
                if len(target_files) >= 1000:
                    break

        for fpath in target_files:
            try:
                rel = str(fpath.relative_to(ctx.workdir)).replace("\\", "/")
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                for line_no, line in enumerate(content.splitlines(), start=1):
                    if compiled_re.search(line):
                        results.append(f"{rel}:{line_no}: {line.strip()[:200]}")
                        if len(results) >= 100:
                            break
            except Exception:
                continue
            if len(results) >= 100:
                break

        if not results:
            return ToolResult.success(f"Không tìm thấy dòng nào khớp với '{args.pattern}'.")

        res_str = f"Kết quả tìm kiếm cho '{args.pattern}' ({len(results)} dòng khớp):\n" + "\n".join(results)
        return ToolResult.success(res_str)
