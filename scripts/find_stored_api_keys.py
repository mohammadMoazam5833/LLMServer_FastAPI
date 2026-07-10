#!/usr/bin/env python3
"""Find gateway API keys (sk-...) saved in common config files on this machine."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


def _scan_text(path: Path, text: str) -> list[str]:
    found = []
    for match in SK_PATTERN.findall(text):
        if match not in found:
            found.append(match)
    return [(path, k) for k in found]


def _scan_file(path: Path) -> list[tuple[Path, str]]:
    if not path.is_file():
        return []
    try:
        return _scan_text(path, path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return []


def _scan_json_api_key(path: Path, *json_paths: str) -> list[tuple[Path, str]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    node = data
    for key in json_paths:
        if not isinstance(node, dict):
            return []
        node = node.get(key)
    if isinstance(node, str) and node.startswith("sk-"):
        return [(path, node)]
    return []


def main() -> None:
    home = Path.home()
    candidates: list[Path] = [
        REPO_ROOT / ".env",
        home / ".openhands" / "settings.json",
        home / ".local" / "share" / "opencode" / "account.json",
    ]

    # Cline / VS Code — common locations
    for base in (
        home / ".config" / "Code" / "User",
        home / ".config" / "Cursor" / "User",
    ):
        candidates.append(base / "settings.json")
        if base.is_dir():
            candidates.extend(base.glob("globalStorage/saoudrizwan.claude-dev/settings/*.json"))

    results: list[tuple[Path, str]] = []
    seen: set[str] = set()

    for path in candidates:
        for p, key in _scan_file(path):
            if key not in seen:
                seen.add(key)
                results.append((p, key))

    oh = home / ".openhands" / "settings.json"
    for p, key in _scan_json_api_key(oh, "agent_settings", "llm", "api_key"):
        if key not in seen:
            seen.add(key)
            results.append((p, key))

    if not results:
        print("No sk- keys found in known config paths.")
        print("Check OpenWebUI UI → Admin → Connections, or create a new key in /admin/api-keys")
        return

    print("Gateway API keys found on this machine:\n")
    for path, key in results:
        print(f"  {path}")
        print(f"    {key}\n")


if __name__ == "__main__":
    main()
