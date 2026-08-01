"""Add llm_llmmodel.base_url for per-model vLLM endpoints.

Revision ID: 20260731_002
Revises: 20260711_001
Create Date: 2026-07-31

Safe for existing databases (uses IF NOT EXISTS).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20260731_002"
down_revision: Union[str, None] = "20260711_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE llm_llmmodel "
        "ADD COLUMN IF NOT EXISTS base_url VARCHAR(512)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE llm_llmmodel DROP COLUMN IF EXISTS base_url")
