"""Initial schema: faculty, venue, time_slot, course, constraint, runs, entries.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "faculty",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("department", sa.String(200), nullable=False, server_default=""),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("max_hours_per_day", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("max_days_per_week", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("unavailable_slots", sa.JSON(), nullable=False),
    )
    op.create_index("ix_faculty_name", "faculty", ["name"])
    op.create_index("ix_faculty_department", "faculty", ["department"])

    op.create_table(
        "venue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("equipment", sa.JSON(), nullable=False),
        sa.Column("available_slots", sa.JSON(), nullable=False),
    )
    op.create_index("ix_venue_name", "venue", ["name"])

    op.create_table(
        "time_slot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day_of_week", sa.String(16), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
    )
    op.create_index("ix_time_slot_day_of_week", "time_slot", ["day_of_week"])

    op.create_table(
        "course",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "faculty_id",
            sa.Integer(),
            sa.ForeignKey("faculty.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("capacity_required", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("required_equipment", sa.JSON(), nullable=False),
    )
    op.create_index("ix_course_name", "course", ["name"])
    op.create_index("ix_course_code", "course", ["code"], unique=True)
    op.create_index("ix_course_faculty_id", "course", ["faculty_id"])

    op.create_table(
        "constraint",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("constraint_data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_constraint_type", "constraint", ["type"])
    op.create_index("ix_constraint_name", "constraint", ["name"])

    op.create_table(
        "schedule_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_courses_scheduled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflicts_resolved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("solver_status", sa.String(32), nullable=False, server_default="unknown"),
    )
    op.create_index("ix_schedule_run_solver_status", "schedule_run", ["solver_status"])

    op.create_table(
        "timetable_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "schedule_run_id",
            sa.Integer(),
            sa.ForeignKey("schedule_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("course.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "faculty_id",
            sa.Integer(),
            sa.ForeignKey("faculty.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "venue_id",
            sa.Integer(),
            sa.ForeignKey("venue.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "slot_id",
            sa.Integer(),
            sa.ForeignKey("time_slot.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("solver_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_timetable_entry_schedule_run_id", "timetable_entry", ["schedule_run_id"])
    op.create_index("ix_timetable_entry_course_id", "timetable_entry", ["course_id"])
    op.create_index("ix_timetable_entry_faculty_id", "timetable_entry", ["faculty_id"])
    op.create_index("ix_timetable_entry_venue_id", "timetable_entry", ["venue_id"])
    op.create_index("ix_timetable_entry_slot_id", "timetable_entry", ["slot_id"])
    op.create_index("ix_timetable_entry_status", "timetable_entry", ["status"])


def downgrade() -> None:
    for table in (
        "timetable_entry",
        "schedule_run",
        "constraint",
        "course",
        "time_slot",
        "venue",
        "faculty",
    ):
        op.drop_table(table)
