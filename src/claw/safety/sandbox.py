from __future__ import annotations

from pathlib import Path


class PathSandbox:
    def __init__(self, workdir: Path | str | None = None) -> None:
        self.workdir = (Path(workdir) if workdir else Path.cwd()).resolve()

    def resolve_safe(self, target_path: str | Path) -> Path:
        """Resolve a path relative to workdir and ensure it does not escape workdir.

        Raises PermissionError if the path escapes workdir or touches sensitive locations.
        """
        p = Path(target_path)
        if not p.is_absolute():
            resolved = (self.workdir / p).resolve()
        else:
            resolved = p.resolve()

        # Check if resolved is within workdir
        try:
            resolved.relative_to(self.workdir)
        except ValueError:
            raise PermissionError(
                f"Đường dẫn '{target_path}' nằm ngoài thư mục làm việc '{self.workdir}'."
            )

        # Protect sensitive files inside workdir
        if resolved.name == ".env" or resolved.name.startswith(".env."):
            raise PermissionError(f"Truy cập tệp nhạy cảm '{resolved.name}' bị hạn chế.")

        return resolved

    def is_safe(self, target_path: str | Path) -> bool:
        try:
            self.resolve_safe(target_path)
            return True
        except (PermissionError, Exception):
            return False
