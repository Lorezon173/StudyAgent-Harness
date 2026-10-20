"""EmbeddingService 单元测试（阶段 A）。

Mock 标注说明：
- 所有外部 API 调用（openai.OpenAI.embeddings.create）均已 mock
- Mock 标注：[MOCK:阶段A]
- Mock 出处：openai.OpenAI.embeddings.create
- 切除方式：用户配置真实 API key 后，运行集成测试（test_pgvector_real.py）验证真实 API 调用
"""

from dataclasses import dataclass
from typing import Any

from app.infrastructure.rag.embedding import EmbeddingService


# [MOCK:阶段A] 假 OpenAI embeddings.create 响应对象
@dataclass
class FakeEmbeddingItem:
    embedding: list[float]
    index: int = 0
    object: str = "embedding"


@dataclass
class FakeEmbeddingResponse:
    data: list[FakeEmbeddingItem]
    model: str = "fake-model"
    object: str = "list"
    usage: dict[str, Any] | None = None


def test_embedding_service_defaults():
    """验证默认配置从 settings 读取。"""
    service = EmbeddingService()
    assert service.model == "doubao-embedding-vision"
    assert service.dim == 2048


def test_embedding_service_custom_config():
    """验证可传入自定义配置。"""
    service = EmbeddingService(
        model="text-embedding-ada-002",
        api_key="test-key",
        base_url="https://test.com"
    )
    assert service.model == "text-embedding-ada-002"
    assert service.api_key == "test-key"
    assert service.base_url == "https://test.com"


def test_embed_one_returns_correct_dimension(monkeypatch):
    """验证 embed_one 返回定长向量（2048）。

    [MOCK:阶段A] Mock openai.OpenAI.embeddings.create
    """
    # [MOCK:阶段A] 构造固定长度的假向量
    fake_embedding = [0.1] * 2048

    class FakeOpenAI:
        def __init__(self, **kwargs):
            pass

        class _embeddings:
            @staticmethod
            def create(model, input, **kwargs):
                return FakeEmbeddingResponse(
                    data=[FakeEmbeddingItem(embedding=fake_embedding) for _ in input]
                )

        embeddings = _embeddings()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    service = EmbeddingService()
    result = service.embed_one("测试文本")

    assert len(result) == 2048
    assert result == fake_embedding


def test_embed_one_empty_text_returns_zero_vector():
    """验证空文本返回零向量。"""
    service = EmbeddingService()
    result = service.embed_one("")

    assert len(result) == 2048
    assert all(x == 0.0 for x in result)


def test_embed_many_batch_processing(monkeypatch):
    """验证 embed_many 批量处理返回正确数量的向量。

    [MOCK:阶段A] Mock openai.OpenAI.embeddings.create
    """
    # [MOCK:阶段A] 为每条文本返回不同的向量（用索引区分）
    class FakeOpenAI:
        def __init__(self, **kwargs):
            pass

        class _embeddings:
            @staticmethod
            def create(model, input, **kwargs):
                return FakeEmbeddingResponse(
                    data=[
                        FakeEmbeddingItem(
                            embedding=[0.1 * (i + 1)] * 2048,
                            index=i,
                        )
                        for i in range(len(input))
                    ]
                )

        embeddings = _embeddings()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    service = EmbeddingService()
    texts = ["文本1", "文本2", "文本3"]
    results = service.embed_many(texts)

    assert len(results) == 3
    assert all(len(vec) == 2048 for vec in results)
    # 验证向量不同（用首个元素区分）
    assert abs(results[0][0] - 0.1) < 1e-9
    assert abs(results[1][0] - 0.2) < 1e-9
    assert abs(results[2][0] - 0.3) < 1e-9


def test_embed_many_empty_list():
    """验证空列表返回空列表。"""
    service = EmbeddingService()
    result = service.embed_many([])
    assert result == []


def test_embed_many_handles_empty_strings(monkeypatch):
    """验证 embed_many 正确处理包含空字符串的列表。

    [MOCK:阶段A] Mock openai.OpenAI.embeddings.create
    """
    # [MOCK:阶段A] 只为非空文本返回向量
    class FakeOpenAI:
        def __init__(self, **kwargs):
            pass

        class _embeddings:
            @staticmethod
            def create(model, input, **kwargs):
                return FakeEmbeddingResponse(
                    data=[
                        FakeEmbeddingItem(embedding=[0.5] * 2048, index=i)
                        for i in range(len(input))
                    ]
                )

        embeddings = _embeddings()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    service = EmbeddingService()
    texts = ["文本1", "", "文本2"]
    results = service.embed_many(texts)

    assert len(results) == 3
    # 第一个和第三个是真实向量
    assert results[0] == [0.5] * 2048
    assert results[2] == [0.5] * 2048
    # 第二个是零向量
    assert results[1] == [0.0] * 2048


def test_embed_many_all_empty_strings():
    """验证全空字符串列表返回全零向量。"""
    service = EmbeddingService()
    texts = ["", "", ""]
    results = service.embed_many(texts)

    assert len(results) == 3
    assert all(vec == [0.0] * 2048 for vec in results)


def test_dim_property():
    """验证 dim 属性正确返回向量维度。"""
    service = EmbeddingService()
    assert service.dim == 2048


def test_lazy_loading_client(monkeypatch):
    """验证 client 懒加载机制（构造时不实例化，首访才实例化且复用）。

    [MOCK:阶段A] Mock openai.OpenAI 为假类
    """
    # [MOCK:阶段A] 用假类替换 OpenAI，追踪实例化次数
    instantiation_count = [0]

    class FakeOpenAI:
        def __init__(self, **kwargs):
            instantiation_count[0] += 1
            self.kwargs = kwargs

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    service = EmbeddingService()
    assert instantiation_count[0] == 0  # 未访问前不应实例化

    _ = service.client  # 第一次访问
    assert instantiation_count[0] == 1

    _ = service.client  # 第二次访问应复用
    assert instantiation_count[0] == 1


def test_settings_fallback(monkeypatch):
    """验证空配置从 settings 兜底。

    [MOCK:阶段A] Mock settings 以验证兜底逻辑
    """
    from app.core import config

    # [MOCK:阶段A] 临时修改 settings
    original_api_key = config.settings.openai_api_key
    original_base_url = config.settings.openai_base_url
    original_model = config.settings.embedding_model

    config.settings.openai_api_key = "settings-key"
    config.settings.openai_base_url = "https://settings.com"
    config.settings.embedding_model = "settings-model"

    try:
        service = EmbeddingService()  # 不传参数
        assert service.api_key == "settings-key"
        assert service.base_url == "https://settings.com"
        assert service.model == "settings-model"
    finally:
        # [MOCK:阶段A] 恢复原始 settings
        config.settings.openai_api_key = original_api_key
        config.settings.openai_base_url = original_base_url
        config.settings.embedding_model = original_model
