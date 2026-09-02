"""RAG-C Phase 2（C-11）：在线 composition 三条件校验（DEC-007）。

在线 API 路径的检索链装配必须满足：
  1. settings.rag_backend == "pgvector"
  2. vector provider 为 PgVectorProvider（显式注入，不依赖默认分支）
  3. DB dialect 为 postgresql

任一不满足 → OnlineRAGCompositionError（分类安全异常），fail-fast，
不静默回退 fake。单元直连 run_new_agent_session 的非在线路径不受限。
"""
import pytest

from app.core.config import settings
from app.orchestration.assembly import (
    OnlineRAGCompositionError,
    build_online_rag_coordinator,
    validate_online_rag_composition,
)


def _patch_online(monkeypatch, backend="pgvector",
                  db_url="postgresql+asyncpg://u:p@localhost:5432/app"):
    monkeypatch.setattr(settings, "rag_backend", backend)
    monkeypatch.setattr(settings, "database_url", db_url)


def test_fake_backend_fail_fast(monkeypatch):
    """默认 fake 后端 → 在线 composition fail-fast（分类错误，不回退）。"""
    _patch_online(monkeypatch, backend="fake")
    with pytest.raises(OnlineRAGCompositionError) as ei:
        build_online_rag_coordinator()
    assert ei.value.error_code == "backend_unavailable"
    assert ei.value.safe_summary == "检索服务当前不可用"


def test_sqlite_dialect_fail_fast(monkeypatch):
    """backend=pgvector 但 DB dialect 为 sqlite → fail-fast。"""
    _patch_online(monkeypatch, backend="pgvector",
                  db_url="sqlite+aiosqlite:///./t.db")
    with pytest.raises(OnlineRAGCompositionError):
        build_online_rag_coordinator()


def test_fake_vector_provider_fail_fast(monkeypatch):
    """vector provider 非 PgVectorProvider（显式 fake 注入）→ fail-fast。"""
    _patch_online(monkeypatch)
    from app.infrastructure.rag.coordinator import IndexProvider, RAGCoordinator

    class _FakeVector(IndexProvider):
        name = "vector"
        def index(self, docs): pass
        def search(self, query, top_k=5, visibility=None): return []
        @property
        def doc_count(self): return 0

    with pytest.raises(OnlineRAGCompositionError):
        validate_online_rag_composition(RAGCoordinator(vector_provider=_FakeVector()))


def test_valid_composition_returns_pgvector_coordinator(monkeypatch):
    """三条件满足 → 返回显式注入 PgVectorProvider 的 Coordinator（不建连接）。"""
    _patch_online(monkeypatch)
    from app.infrastructure.rag.pgvector_provider import PgVectorProvider
    coord = build_online_rag_coordinator()
    vector = coord.get_provider("vector")
    assert isinstance(vector, PgVectorProvider)
    assert vector.dialect_name == "postgresql"
    assert vector._conn is None  # 懒连接：校验不触碰真实 DB


def test_run_online_agent_session_fail_fast_before_loop(monkeypatch):
    """composition 失败在协作环之前抛出（不进入种子/检索）。"""
    _patch_online(monkeypatch, backend="fake")
    from app.orchestration.assembly import run_online_agent_session
    with pytest.raises(OnlineRAGCompositionError):
        run_online_agent_session("s", 1, "hi")


def test_build_new_stack_accepts_injected_retriever():
    """build_new_stack 支持注入在线 RetrieverAgent（显式入口、最小参数）。"""
    from app.agents.retriever import RetrieverAgent
    from app.orchestration.assembly import build_new_stack

    retriever = RetrieverAgent()
    bus, orchestrator, store = build_new_stack(1, retriever=retriever)
    try:
        assert bus is not None and orchestrator is not None
    finally:
        store.close()
