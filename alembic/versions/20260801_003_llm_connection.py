"""Add llm_llmconnection + llm_llmmodel.connection_id.

Revision ID: 20260801_003
Revises: 20260731_002
Create Date: 2026-08-01

Safe for existing databases (IF NOT EXISTS).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20260801_003"
down_revision: Union[str, None] = "20260731_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_llmconnection (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            provider_type VARCHAR(64) NOT NULL DEFAULT 'openai_compatible',
            base_url VARCHAR(512) NOT NULL,
            api_key_encrypted TEXT,
            api_key_hint VARCHAR(32) DEFAULT '',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "ALTER TABLE llm_llmmodel "
        "ADD COLUMN IF NOT EXISTS connection_id VARCHAR(64)"
    )
    # FK may already exist on re-run; ignore failures via DO block
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_llmmodel_connection'
            ) THEN
                ALTER TABLE llm_llmmodel
                    ADD CONSTRAINT fk_llmmodel_connection
                    FOREIGN KEY (connection_id)
                    REFERENCES llm_llmconnection(id)
                    ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_llm_llmmodel_connection_id "
        "ON llm_llmmodel (connection_id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE llm_llmmodel DROP CONSTRAINT IF EXISTS fk_llmmodel_connection")
    op.execute("DROP INDEX IF EXISTS ix_llm_llmmodel_connection_id")
    op.execute("ALTER TABLE llm_llmmodel DROP COLUMN IF EXISTS connection_id")
    op.execute("DROP TABLE IF EXISTS llm_llmconnection")
