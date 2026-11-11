from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.sql import func

from app.core.database import Base


class UserTable(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class SessionTable(Base):
    __tablename__ = "sessions"
    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    state_json = Column(Text, nullable=False)
    title = Column(String(128), default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    profile_id = Column(String(36), nullable=True)
    active_node_id = Column(String(36), nullable=True)
    workspace_entered = Column(Boolean, nullable=False, default=False, server_default=false())
    state_version = Column(Integer, nullable=False, default=0, server_default="0")
    next_turn_index = Column(Integer, nullable=False, default=0, server_default="0")
    active_request_id = Column(String(64), nullable=True)
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_session_owner"),
        UniqueConstraint("user_id", "id", "profile_id", name="uq_session_profile_owner"),
        ForeignKeyConstraint(["user_id", "profile_id"], ["topic_profiles.user_id", "topic_profiles.id"], name="fk_session_profile_owner"),
        ForeignKeyConstraint(["profile_id", "active_node_id"], ["profile_nodes.profile_id", "profile_nodes.id"], name="fk_session_active_node"),
        ForeignKeyConstraint(["user_id", "id", "active_request_id"], ["chat_requests.user_id", "chat_requests.session_id", "chat_requests.request_id"], name="fk_session_active_request", use_alter=True),
        CheckConstraint("profile_id IS NULL OR user_id IS NOT NULL", name="ck_session_profile_owner"),
        CheckConstraint("active_node_id IS NULL OR profile_id IS NOT NULL", name="ck_session_node_profile"),
        CheckConstraint("active_request_id IS NULL OR user_id IS NOT NULL", name="ck_session_request_owner"),
        CheckConstraint("state_version >= 0 AND next_turn_index >= 0", name="ck_session_versions"),
    )


class MessageTable(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id"), index=True, nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    turn_index = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("session_id", "id", name="uq_message_session_id"),
        UniqueConstraint("session_id", "turn_index", "role",
                         name="uq_message_turn"),
    )


class KnowledgeTable(Base):
    __tablename__ = "knowledge"
    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(16), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    source = Column(String(256), default="")
    doc_ids = Column(JSON, default=list)
    created_at = Column(DateTime, server_default=func.now())


class EvalTable(Base):
    __tablename__ = "evals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id"), nullable=False)
    mastery_score = Column(Integer, default=0)
    mastery_level = Column(String(16), default="")
    ragas_faithfulness = Column(Float, nullable=True)
    ragas_relevancy = Column(Float, nullable=True)
    ragas_context_precision = Column(Float, nullable=True)
    ragas_context_recall = Column(Float, nullable=True)
    eval_data = Column(JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now())


class MasteryNodeTable(Base):
    __tablename__ = "mastery_nodes"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    topic_id = Column(String(512), primary_key=True)
    topic_name = Column(String(512), nullable=False, default="")
    mastery = Column(Float, nullable=False, default=0.0)
    last_practiced_at = Column(Float, nullable=False, default=0.0)
    practice_count = Column(Integer, nullable=False, default=0)
    confusion_with = Column(JSON, nullable=False, default=list)
    rationale = Column(Text, nullable=False, default="")


class MasteryEdgeTable(Base):
    __tablename__ = "mastery_edges"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    from_topic = Column(String(512), nullable=False)
    to_topic = Column(String(512), nullable=False)
    type = Column(String(16), nullable=False, default="PREREQ")
    weight = Column(Float, nullable=False, default=1.0)
    confidence = Column(Float, nullable=False, default=0.5)
    source = Column(String(16), nullable=False, default="LLM_INFER")
    __table_args__ = (
        UniqueConstraint("user_id", "from_topic", "to_topic", "type",
                         name="uq_mastery_edge"),
    )


class VectorChunkTable(Base):
    """向量检索表 —— 存储 chunk 文本 + embedding + 元数据（阶段 A）。

    字段设计：
      - user_id/scope: 多用户 + global/personal 知识范围（对齐 KnowledgeTable）
      - content: chunk 原文
      - embedding: 向量（PG 用 pgvector.Vector，sqlite 退化为 JSON）
      - source: "vector" | "ocr" | "code"（对齐 Chunk.source）
      - doc_id/metadata: 文档标识 + 元信息（file_path/page/chunk_idx 等）
    """
    __tablename__ = "vector_chunks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    scope = Column(String(16), nullable=False, default="global", index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(2048), nullable=True)  # PG: vector(2048); sqlite: 迁移时退化为 TEXT
    source = Column(String(16), nullable=False, default="vector")
    doc_id = Column(String(256), default="")
    chunk_id = Column(String(256), nullable=True)
    metadata_json = Column(JSON, default=dict)  # 不能用 'metadata'（SQLAlchemy 保留字）
    created_at = Column(DateTime, server_default=func.now())
