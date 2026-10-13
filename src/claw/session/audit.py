from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AuditEntry:
    timestamp: str
    tool_name: str
    args: dict[str, Any]
    risk_level: str
    decision: str  # auto_approved, user_approved, user_rejected, policy_denied
    reason: str
    workdir: str
    user_input: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class AuditLogger:
    def __init__(self, audit_file: Path | str) -> None:
        self.audit_path = Path(audit_file)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        tool_name: str,
        args: dict[str, Any],
        risk_level: str,
        decision: str,
        reason: str,
        workdir: str,
        user_input: str = "",
    ) -> None:
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_name=tool_name,
            args=args,
            risk_level=risk_level,
            decision=decision,
            reason=reason,
            workdir=workdir,
            user_input=user_input,
        )
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(entry.to_json() + "\n")
        except Exception:
            # Audit failure shouldn't crash the assistant
            pass
