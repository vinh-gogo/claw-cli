from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claw.llm.schema import Message, ToolCall


class SessionStore:
    def __init__(self, sessions_dir: Path | str) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create_session_id(self) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        short_id = uuid.uuid4().hex[:6]
        return f"{timestamp}-{short_id}"

    def get_session_file(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.jsonl"

    def save_turn(self, session_id: str, messages: list[Message]) -> None:
        session_file = self.get_session_file(session_id)
        with open(session_file, "w", encoding="utf-8") as f:
            for m in messages:
                line_data = m.to_openai_dict()
                f.write(json.dumps(line_data, ensure_ascii=False) + "\n")

    def load_session(self, session_id: str) -> list[Message]:
        session_file = self.get_session_file(session_id)
        if not session_file.is_file():
            # Try finding prefix match
            matches = list(self.sessions_dir.glob(f"*{session_id}*.jsonl"))
            if matches:
                session_file = matches[0]
            else:
                raise FileNotFoundError(f"Phiên làm việc '{session_id}' không tồn tại.")

        messages: list[Message] = []
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                tool_calls: list[ToolCall] | None = None
                if "tool_calls" in data and data["tool_calls"]:
                    tool_calls = []
                    for tc in data["tool_calls"]:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", "{}")
                        tool_calls.append(
                            ToolCall(
                                id=tc.get("id", ""),
                                name=fn.get("name", ""),
                                arguments=args,
                            )
                        )
                messages.append(
                    Message(
                        role=data.get("role", "user"),
                        content=data.get("content"),
                        tool_calls=tool_calls,
                        tool_call_id=data.get("tool_call_id"),
                        name=data.get("name"),
                    )
                )
        return messages

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for p in sorted(self.sessions_dir.glob("*.jsonl"), reverse=True):
            stat = p.stat()
            sessions.append(
                {
                    "session_id": p.stem,
                    "path": str(p),
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        return sessions
