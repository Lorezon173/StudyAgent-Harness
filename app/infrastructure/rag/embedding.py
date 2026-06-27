"""EmbeddingService —— 统一的文本→向量入口（阶段 A）。

职责：
  - 将文本（单条/批量）转成定长 float 向量
  - 为 PgVectorProvider 提供 embedding 能力
  - 复用现有 OpenAI 配置（api_key/base_url）

设计要点：
  - 懒加载 embedding client（仿 LLMService.llm 的 lazy property）
  - 空字段从 settings 兜底（仿 LLMService._apply_settings_fallback）
  - 无状态，线程安全
"""

from app.core.config import settings


class EmbeddingService:
    """文本 embedding 服务，复用 OpenAI 配置。"""

    def __init__(self, model: str = "", api_key: str = "", base_url: str = ""):
        """初始化 embedding 服务。

        Args:
            model: embedding 模型名（空则从 settings.embedding_model 读取）
            api_key: OpenAI API key（空则从 settings.openai_api_key 读取）
            base_url: OpenAI base URL（空则从 settings.openai_base_url 读取）
        """
        self.model = model or settings.embedding_model
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url or settings.openai_base_url
        self._client = None

    @property
    def dim(self) -> int:
        """返回当前模型的向量维度。"""
        return settings.embedding_dim

    @property
    def client(self):
        """懒加载 OpenAI embedding client。"""
        if self._client is None:
            from langchain_openai import OpenAIEmbeddings
            self._client = OpenAIEmbeddings(
                model=self.model,
                openai_api_key=self.api_key,
                openai_api_base=self.base_url or None,
            )
        return self._client

    def embed_one(self, text: str) -> list[float]:
        """将单条文本转成向量。

        Args:
            text: 输入文本

        Returns:
            长度为 dim 的 float 向量
        """
        if not text:
            return [0.0] * self.dim
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """批量将文本转成向量。

        Args:
            texts: 文本列表

        Returns:
            向量列表，每个向量长度为 dim
        """
        if not texts:
            return []
        # 过滤空文本，保持索引对应关系
        non_empty_indices = [i for i, t in enumerate(texts) if t]
        non_empty_texts = [texts[i] for i in non_empty_indices]

        if not non_empty_texts:
            return [[0.0] * self.dim] * len(texts)

        embeddings = self.client.embed_documents(non_empty_texts)

        # 将结果映射回原始索引位置
        result = []
        embed_idx = 0
        for i, text in enumerate(texts):
            if text:
                result.append(embeddings[embed_idx])
                embed_idx += 1
            else:
                result.append([0.0] * self.dim)

        return result
