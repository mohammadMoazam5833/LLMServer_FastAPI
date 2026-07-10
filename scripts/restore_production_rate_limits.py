#!/usr/bin/env python3
"""
بازگرداندن rate limit کلیدهای API برای محیط production.

پس از load test معمولاً limit روی ۰ مانده یا LOAD_TEST_DISABLE_RATE_LIMIT فعال بوده.
این اسکریپت کلیدهای فعال با limit غیرفعال (۰) یا پایین (≤۶۰) را به مقدار production
تنظیم می‌کند (پیش‌فرض: ۱۸۰ req/min — مناسب ~۱۵ کاربر همزمان با Cline/OpenWebUI).

Usage:
  python scripts/restore_production_rate_limits.py
  python scripts/restore_production_rate_limits.py --limit 240
  python scripts/restore_production_rate_limits.py --all   # همه کلیدهای فعال
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select, update

sys.path.insert(0, ".")

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.api_key import APIKey


async def main(limit: int, all_keys: bool) -> None:
    settings = get_settings()
    print(f"Database: {settings.DATABASE_URL.split('@')[-1]}")
    print(f"Target rate limit: {limit} req/min per key")
    if settings.LOAD_TEST_DISABLE_RATE_LIMIT:
        print("⚠️  LOAD_TEST_DISABLE_RATE_LIMIT=true — rate limit در runtime غیرفعال است!")
        print("   در .env آن را false کنید یا خط را حذف کنید.")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(APIKey).where(APIKey.is_active == True))  # noqa: E712
        keys = result.scalars().all()

        if not keys:
            print("No active API keys found.")
            sys.exit(1)

        updated = 0
        for key in keys:
            should_update = all_keys or key.rate_limit_per_minute <= 0 or key.rate_limit_per_minute <= 60
            if not should_update:
                print(f"  skip id={key.id} name={key.name!r} limit={key.rate_limit_per_minute}")
                continue
            await db.execute(
                update(APIKey).where(APIKey.id == key.id).values(rate_limit_per_minute=limit)
            )
            print(f"  updated id={key.id} name={key.name!r} {key.rate_limit_per_minute} -> {limit}")
            updated += 1

        await db.commit()

    print(f"Done. {updated} key(s) updated.")


if __name__ == "__main__":
    default_limit = get_settings().DEFAULT_RATE_LIMIT_PER_MINUTE
    parser = argparse.ArgumentParser(description="Restore production API key rate limits")
    parser.add_argument("--limit", type=int, default=default_limit, help="Requests per minute")
    parser.add_argument("--all", action="store_true", help="Update all active keys, not only 0/60")
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.all))
