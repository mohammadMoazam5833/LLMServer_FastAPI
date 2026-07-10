#!/usr/bin/env python3
"""Reset password for a gateway user (default: admin)."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)

from sqlalchemy import select

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.user import User


async def main(username: str, password: str, make_superuser: bool) -> None:
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                username=username,
                email=f"{username}@local",
                password=hash_password(password),
                is_active=True,
                is_staff=True,
                is_superuser=True,
            )
            db.add(user)
            action = "created"
        else:
            user.password = hash_password(password)
            user.is_active = True
            if make_superuser:
                user.is_superuser = True
                user.is_staff = True
            action = "updated"
        await db.commit()
        print(f"OK: {action} user '{username}' (superuser={user.is_superuser})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset gateway user password")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--superuser", action="store_true", default=True)
    args = parser.parse_args()
    asyncio.run(main(args.username, args.password, args.superuser))
