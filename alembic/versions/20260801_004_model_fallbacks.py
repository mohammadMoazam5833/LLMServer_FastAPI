"""Add llm_llmmodel.fallback_model_ids for LiteLLM-style fallbacks.

Revision ID: 20260801_004
Revises: 20260801_003
Create Date: 2026-08-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20260801_004"
down_revision: Union[str, None] = "20260801_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE llm_llmmodel "
        "ADD COLUMN IF NOT EXISTS fallback_model_ids JSONB DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE llm_llmmodel DROP COLUMN IF EXISTS fallback_model_ids")
