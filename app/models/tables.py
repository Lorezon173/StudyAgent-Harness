from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON, ForeignKey, UniqueConstraint
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


class MessageTable(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id"), index=True, nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    turn_index = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


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
    eval_data = Column(JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now())


class MasteryNodeTable(Base):
    __tablename__ = "mastery_nodes"
    user_id = Column(String(64), primary_key=True)
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
    user_id = Column(String(64), nullable=False, index=True)
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
