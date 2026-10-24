"""工作区主题画像；历史 mastery 表继续独立保留。"""
from uuid import uuid4

from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, Float,
                        ForeignKey, ForeignKeyConstraint, Index, Integer,
                        String, Text, UniqueConstraint, text)
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
