"""
app/db/models.py
Minimal system DB schema for Phase 0.

Every user-scoped table carries a user_id column. Vasuki must never assume
there is exactly one user — this is a hard architectural rule, not a
suggestion. Multi-user support from day one is core to treating Vasuki
as a real product rather than personal tooling.
"""
import sqlalchemy as sa

metadata = sa.MetaData()

speaker_profiles = sa.Table(
    "speaker_profiles",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("user_id", sa.String, nullable=False, unique=True, index=True),
    sa.Column("display_name", sa.String, nullable=True),
    sa.Column("embedding_path", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
)

command_history = sa.Table(
    "command_history",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("user_id", sa.String, nullable=False, index=True),
    sa.Column("transcript", sa.String, nullable=True),
    sa.Column("intent", sa.String, nullable=True),
    sa.Column("params_json", sa.String, nullable=True),
    sa.Column("result", sa.String, nullable=True),
    sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
)

audit_log = sa.Table(
    "audit_log",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("user_id", sa.String, nullable=True, index=True),
    sa.Column("event_type", sa.String, nullable=False),
    sa.Column("detail", sa.String, nullable=True),
    sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
)

intruder_lockouts = sa.Table(
    "intruder_lockouts",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("locked_until", sa.DateTime, nullable=False),
    sa.Column("fail_count", sa.Integer, nullable=False, default=0),
    sa.Column("last_similarity", sa.Float, nullable=True),
    sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
)

audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("event", sa.String, nullable=False),
    sa.Column("user_id", sa.String, nullable=True),
    sa.Column("action", sa.String, nullable=True),
    sa.Column("success", sa.Boolean, nullable=True),
    sa.Column("detail", sa.String, nullable=True),
    sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
)

app_index = sa.Table(
    "app_index",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String, nullable=False, index=True),
    sa.Column("path", sa.String, nullable=False),
    sa.Column("source", sa.String, nullable=False),
    sa.Column("indexed_at", sa.DateTime, server_default=sa.func.now()),
)

