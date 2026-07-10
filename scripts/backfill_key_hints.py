#!/usr/bin/env python3
"""Add key_hint column and backfill from keys found in local config files."""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from sqlalchemy import select, text

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core.security import hash_api_key, mask_api_key, encrypt_api_key  # noqa: E402
from app.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.api_key import APIKey  # noqa: E402

SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


def _collect_keys_from_disk() -> dict[str, str]:
    """hash -> raw key (from local configs only)."""
    home = Path.home()
    paths = [
        REPO_ROOT / ".env",
        home / ".openhands" / "settings.json",
        home / ".local" / "share" / "opencode" / "account.json",
    ]
    out: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            continue
        try:
            text_content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for raw in SK_PATTERN.findall(text_content):
            out[hash_api_key(raw)] = raw
    return out


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE api_keys_apikey "
                "ADD COLUMN IF NOT EXISTS key_hint VARCHAR(32) DEFAULT ''"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE api_keys_apikey "
                "ADD COLUMN IF NOT EXISTS key_encrypted VARCHAR(512) DEFAULT ''"
            )
        )

    known = _collect_keys_from_disk()
    updated = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(APIKey))
        keys = list(result.scalars().all())
        for api_key in keys:
            raw = known.get(api_key.key_hash)
            if not raw:
                continue
            changed = False
            if not api_key.key_hint:
                api_key.key_hint = mask_api_key(raw)
                changed = True
            if not api_key.key_encrypted:
                api_key.key_encrypted = encrypt_api_key(raw)
                changed = True
            if changed:
                updated += 1
        await db.commit()

    print(f"OK: backfilled {updated} key(s) from local config files.")
    print(f"    ({len(known)} unique sk- key(s) found on disk)")
    missing = sum(1 for k in keys if not k.key_encrypted)
    if missing:
        print(f"    {missing} key(s) still without stored secret — recreate if needed.")


if __name__ == "__main__":
    asyncio.run(main())
