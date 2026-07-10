"""Add key_hint and key_encrypted columns for admin API key display.

Revision ID: 20260711_001
Revises:
Create Date: 2026-07-11

Safe for existing databases (uses IF NOT EXISTS).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20260711_001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE api_keys_apikey "
        "ADD COLUMN IF NOT EXISTS key_hint VARCHAR(32) DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE api_keys_apikey "
        "ADD COLUMN IF NOT EXISTS key_encrypted VARCHAR(512) DEFAULT ''"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE api_keys_apikey DROP COLUMN IF EXISTS key_encrypted")
    op.execute("ALTER TABLE api_keys_apikey DROP COLUMN IF EXISTS key_hint")
