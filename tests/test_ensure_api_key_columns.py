"""Tests for startup schema helpers (AUTO_CREATE_TABLES=false safe path)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from app import database


class _FakeEngine:
    def __init__(self, table_exists: bool):
        self.table_exists = table_exists
        self.executes: list[str] = []

    def begin(self):
        engine = self

        @asynccontextmanager
        async def _begin():
            class FakeConn:
                async def scalar(self, statement):
                    sql = str(statement)
                    assert "to_regclass" in sql
                    return engine.table_exists

                async def execute(self, statement):
                    engine.executes.append(str(getattr(statement, "text", statement)))

            yield FakeConn()

        return _begin()


def test_ensure_api_key_columns_skips_when_table_missing():
    fake = _FakeEngine(table_exists=False)
    asyncio.run(database.ensure_api_key_columns(bind=fake))
    assert fake.executes == []


def test_ensure_api_key_columns_alters_when_table_exists():
    fake = _FakeEngine(table_exists=True)
    asyncio.run(database.ensure_api_key_columns(bind=fake))
    assert len(fake.executes) == 2
    assert all("ALTER TABLE api_keys_apikey" in sql for sql in fake.executes)
    assert any("key_hint" in sql for sql in fake.executes)
    assert any("key_encrypted" in sql for sql in fake.executes)
