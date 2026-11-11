"""工作区主题画像；历史 mastery 表继续独立保留。"""
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.sql import func

from app.core.database import Base


class TopicProfileTable(Base):
    __tablename__ = "topic_profiles"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    scope_description = Column(Text, nullable=False, default="", server_default="")
    kind = Column(String(16), nullable=False, default="normal", server_default="normal")
    revision = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_topic_profile_owner"),
        CheckConstraint("kind IN ('normal', 'legacy')", name="ck_topic_profile_kind"),
        CheckConstraint("revision >= 0", name="ck_topic_profile_revision"),
        Index("uq_topic_profile_legacy_owner", "user_id", unique=True,
              sqlite_where=text("kind = 'legacy'"), postgresql_where=text("kind = 'legacy'")),
    )


class ProfileNodeTable(Base):
    __tablename__ = "profile_nodes"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    profile_id = Column(String(36), ForeignKey("topic_profiles.id"), nullable=False, index=True)
    title = Column(String(512), nullable=False, default="", server_default="")
    description = Column(Text, nullable=False, default="", server_default="")
    mastery = Column(Float, nullable=True)
    last_practiced_at = Column(Float, nullable=False, default=0.0, server_default="0")
    practice_count = Column(Integer, nullable=False, default=0, server_default="0")
    rationale = Column(Text, nullable=False, default="", server_default="")
    revision = Column(Integer, nullable=False, default=0, server_default="0")
    archived = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    __table_args__ = (
        UniqueConstraint("profile_id", "id", name="uq_profile_node_scope"),
        CheckConstraint("revision >= 0", name="ck_profile_node_revision"),
    )


class ProfileEdgeTable(Base):
    __tablename__ = "profile_edges"
    profile_id = Column(String(36), ForeignKey("topic_profiles.id"), primary_key=True)
    from_node_id = Column(String(36), primary_key=True)
    to_node_id = Column(String(36), primary_key=True)
    type = Column(String(16), primary_key=True, default="PREREQ", server_default="PREREQ")
    weight = Column(Float, nullable=False, default=1.0, server_default="1")
    confidence = Column(Float, nullable=False, default=0.5, server_default="0.5")
    source = Column(String(16), nullable=False, default="LLM_INFER", server_default="LLM_INFER")
    __table_args__ = (
        ForeignKeyConstraint(["profile_id", "from_node_id"], ["profile_nodes.profile_id", "profile_nodes.id"],
                             name="fk_profile_edge_from_node"),
        ForeignKeyConstraint(["profile_id", "to_node_id"], ["profile_nodes.profile_id", "profile_nodes.id"],
                             name="fk_profile_edge_to_node"),
    )


class ChatRequestTable(Base):
    __tablename__ = "chat_requests"
    user_id = Column(Integer, primary_key=True)
    session_id = Column(String(64), primary_key=True)
    request_id = Column(String(64), primary_key=True)
    profile_id = Column(String(36), nullable=False)
    active_node_id = Column(String(36), nullable=True)
    payload_hash = Column(String(128), nullable=False)
    request_payload = Column(JSON, nullable=False)
    base_state_version = Column(Integer, nullable=False)
    attempt = Column(Integer, nullable=False, default=1, server_default="1")
    status = Column(String(16), nullable=False)
    lease_until = Column(DateTime, nullable=True)
    error_code = Column(String(64), nullable=True)
    response_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", "request_id", "profile_id", name="uq_request_profile_scope"),
        ForeignKeyConstraint(["user_id", "session_id", "profile_id"], ["sessions.user_id", "sessions.id", "sessions.profile_id"], name="fk_request_session_scope"),
        ForeignKeyConstraint(["profile_id", "active_node_id"], ["profile_nodes.profile_id", "profile_nodes.id"], name="fk_request_node_scope"),
        CheckConstraint("status IN ('running', 'completed', 'failed', 'interrupted')", name="ck_request_status"),
        CheckConstraint("attempt >= 1 AND base_state_version >= 0", name="ck_request_versions"),
        CheckConstraint("status != 'running' OR lease_until IS NOT NULL", name="ck_request_running_lease"),
    )


class ProfileEvidenceTable(Base):
    __tablename__ = "profile_evidence"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(Integer, nullable=False)
    profile_id = Column(String(36), nullable=False)
    node_id = Column(String(36), nullable=False)
    session_id = Column(String(64), nullable=False)
    request_id = Column(String(64), nullable=False)
    message_id = Column(Integer, nullable=False)
    score = Column(Float, nullable=False)
    rationale = Column(Text, nullable=False, default="", server_default="")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", "request_id", "node_id", name="uq_profile_evidence_request_node"),
        ForeignKeyConstraint(["user_id", "session_id", "request_id", "profile_id"], ["chat_requests.user_id", "chat_requests.session_id", "chat_requests.request_id", "chat_requests.profile_id"], name="fk_evidence_request_scope"),
        ForeignKeyConstraint(["profile_id", "node_id"], ["profile_nodes.profile_id", "profile_nodes.id"], name="fk_evidence_node_scope"),
        ForeignKeyConstraint(["session_id", "message_id"], ["messages.session_id", "messages.id"], name="fk_evidence_message_scope"),
    )


class SessionViewStateTable(Base):
    __tablename__ = "session_view_states"
    user_id = Column(Integer, primary_key=True)
    session_id = Column(String(64), primary_key=True)
    draft = Column(Text, nullable=False, default="", server_default="")
    reading_anchor = Column(JSON, nullable=True)
    version = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "session_id"], ["sessions.user_id", "sessions.id"], name="fk_session_view_owner"),
        CheckConstraint("version >= 0", name="ck_session_view_version"),
    )


class UserWorkspaceStateTable(Base):
    __tablename__ = "user_workspace_states"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    last_session_id = Column(String(64), nullable=True)
    sidebar_pinned = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    sidebar_collapsed = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    progress_y_ratio = Column(Float, nullable=False, default=0.5, server_default="0.5")
    version = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "last_session_id"], ["sessions.user_id", "sessions.id"], name="fk_workspace_last_session_owner"),
        CheckConstraint("progress_y_ratio >= 0 AND progress_y_ratio <= 1", name="ck_workspace_progress_ratio"),
        CheckConstraint("version >= 0", name="ck_workspace_version"),
    )


class LibraryItemTable(Base):
    __tablename__ = "library_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    profile_id = Column(String(36), nullable=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False, default="", server_default="")
    content_text = Column(Text, nullable=False, default="", server_default="")
    source_type = Column(String(16), nullable=False, default="manual", server_default="manual")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "profile_id"], ["topic_profiles.user_id", "topic_profiles.id"], name="fk_library_profile_owner"),
        Index("ix_library_owner_id", "user_id", "id"),
        Index("ix_library_owner_profile_id", "user_id", "profile_id", "id"),
    )
