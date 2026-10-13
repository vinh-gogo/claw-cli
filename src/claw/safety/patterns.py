from __future__ import annotations

import re
from typing import Literal

RiskLevel = Literal["none", "read", "low", "input", "write", "exec", "dangerous"]

RISK_ORDER: dict[RiskLevel, int] = {
    "none": 0,
    "read": 1,
    "low": 2,
    "input": 3,
    "write": 4,
    "exec": 5,
    "dangerous": 6,
}

DANGEROUS_PATTERNS = [
    # Recursive/forced removal
    r"\brm\s+.*-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\b",
    r"\brm\s+.*--(?:recursive|force)\b",
    r"\brm\s+-[a-zA-Z]*r\b",
    r"\brmdir\s+/[sS]\b",
    r"\bdel\s+.*(?:/[fF]|/[sS]|/[qQ])\b",
    # Privilege escalation
    r"\bsudo\b",
    r"\bsu\b",
    r"\brunas\b",
    # Destructive git commands
    r"\bgit\s+push\s+.*(?:--force|-f)\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+.*-[a-zA-Z]*f",
    r"\bgit\s+branch\s+-[a-zA-Z]*D\b",
    # System disk / permission alteration
    r"\bdd\s+if=",
    r"\bmkfs\b",
    r"\bfdisk\b",
    r"\bformat\s+[a-zA-Z]:",
    r"\bchmod\s+.*-[a-zA-Z]*R\b",
    r"\bchown\s+.*-[a-zA-Z]*R\b",
    # Pipe to shell execution
    r"\|\s*(?:bash|sh|zsh|pwsh|powershell)\b",
    # Fork bomb
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    # Sensitive file touches / edits
    r">\s*.*\.env\b",
    r">\s*.*id_rsa\b",
    r">\s*/etc/",
    r">\s*C:\\Windows",
]

READ_PATTERNS = [
    r"^(?:ls|dir|cat|head|tail|grep|find|wc|pwd|echo|which|where|type)\b",
    r"^git\s+(?:status|log|diff|branch|show|remote|tag|ls-files)\b",
    r"^pytest\s+.*--collect-only\b",
    r"^python\s+-m\s+unittest\s+discover\s+--help\b",
    r"^cargo\s+check\b",
]


def split_compound_command(cmd: str) -> list[str]:
    """Break compound command into individual commands by splitting on &&, ||, ;, |, and extracting subshells $(...)."""
    parts: list[str] = []

    # Extract subshells $(...) and `...`
    subshells = re.findall(r"\$\((.*?)\)", cmd) + re.findall(r"`(.*?)`", cmd)
    for sub in subshells:
        parts.extend(split_compound_command(sub))

    # Clean out subshell content before splitting to avoid false separator splits
    cleaned_cmd = re.sub(r"\$\(.*?\)", "", cmd)
    cleaned_cmd = re.sub(r"`.*?`", "", cleaned_cmd)

    # Split by &&, ||, ;, and |
    raw_tokens = re.split(r"(?:&&|\|\||;|\|)", cleaned_cmd)
    for t in raw_tokens:
        t = t.strip()
        if t:
            parts.append(t)

    return parts if parts else [cmd.strip()]


def classify_single_command(cmd: str) -> RiskLevel:
    """Classify risk of a single shell command without compound operators."""
    cmd = cmd.strip()
    if not cmd:
        return "none"

    # 1. Check dangerous patterns first
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return "dangerous"

    # Check redirection into files
    if ">" in cmd or ">>" in cmd:
        return "write"

    # 2. Check read patterns
    for pattern in READ_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return "read"

    # Default for unknown commands is exec
    return "exec"


def classify_shell_command(cmd: str) -> RiskLevel:
    """Classify the overall risk level of a shell command (compound or single).

    The highest risk level of all components is returned.
    """
    cmd_clean = cmd.strip()
    if not cmd_clean:
        return "none"

    # Check dangerous patterns on the full un-split command first (e.g. pipe to bash/sh)
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_clean, re.IGNORECASE):
            return "dangerous"

    parts = split_compound_command(cmd_clean)
    max_risk: RiskLevel = "read"

    for part in parts:
        part_risk = classify_single_command(part)
        if RISK_ORDER[part_risk] > RISK_ORDER[max_risk]:
            max_risk = part_risk

    return max_risk
