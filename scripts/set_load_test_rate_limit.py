#!/usr/bin/env python3
"""
Raise or disable per-minute rate limit for load-test API keys.

Usage:
  python scripts/set_load_test_rate_limit.py --limit 0          # disable (recommended for Locust)
  python scripts/set_load_test_rate_limit.py --limit 5000     # high ceiling
  python scripts/set_load_test_rate_limit.py --name load-test  # filter by key name

Requires DATABASE_URL in environment or .env (same as the gateway).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select, update

# Allow running from repo root
sys.path.insert(0, ".")

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.api_key import APIKey


async def main(limit: int, name: str | None) -> None:
    settings = get_settings()
    print(f"Database: {settings.DATABASE_URL.split('@')[-1]}")

    async with AsyncSessionLocal() as db:
        q = select(APIKey).where(APIKey.is_active == True)  # noqa: E712
        if name:
            q = q.where(APIKey.name == name)
        result = await db.execute(q)
        keys = result.scalars().all()

        if not keys:
            print("No matching active API keys found.")
            if name:
                print(f"  filter name={name!r}")
            sys.exit(1)

        for key in keys:
            await db.execute(
                update(APIKey)
                .where(APIKey.id == key.id)
                .values(rate_limit_per_minute=limit)
            )
            print(
                f"Updated key id={key.id} name={key.name!r} "
                f"rate_limit_per_minute -> {limit}"
            )
        await db.commit()

    if limit <= 0:
        print("Rate limit disabled for selected key(s) (0 = unlimited in enforce_rate_limit).")
    else:
        print(f"Rate limit set to {limit} requests/minute per key.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set API key rate limit for load testing")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Requests per minute (0 = disable rate limit)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Only update keys with this name (optional)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.name))
