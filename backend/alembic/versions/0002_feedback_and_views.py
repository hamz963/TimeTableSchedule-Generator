"""Feedback tables + run summary labels for views/exports.

Revision ID: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "schedule_run_id",
            sa.Integer(),
            sa.ForeignKey("schedule_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("teacher_name", sa.String(200), nullable=False),
        sa.Column("satisfaction_score", sa.Integer(), nullable=False),
        sa.Column("preferred_time", sa.String(32), nullable=False, server_default=""),
        sa.Column("workload_satisfaction", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("comments", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_feedback_schedule_run_id", "feedback", ["schedule_run_id"])
    op.create_index("ix_feedback_teacher_name", "feedback", ["teacher_name"])

    op.create_table(
        "ml_model",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column(
            "trained_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("training_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accuracy", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("params", sa.JSON(), nullable=False),
    )
    op.create_index("ix_ml_model_version", "ml_model", ["version"])

    op.add_column("schedule_run", sa.Column("summary_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("schedule_run", "summary_data")
    op.drop_table("ml_model")
    op.drop_table("feedback")
