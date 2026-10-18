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
        dimension = settings.embedding_dim
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
            raise ValueError("embedding_dim 必须为正整数")
        self._dim = dimension
        self._client = None

    @property
    def dim(self) -> int:
        """返回实例创建时绑定的向量维度。"""
        return self._dim

    @property
    def client(self):
        """懒加载 OpenAI embedding client（直接用 OpenAI SDK，避免 langchain 预分词问题）。"""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url or None,
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

        # 分批调用 API（方舟限制：单次最多 10 条）
        batch_size = 10
        all_embeddings = []
        for i in range(0, len(non_empty_texts), batch_size):
            batch = non_empty_texts[i:i + batch_size]
            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            data = getattr(response, "data", None)
            if not isinstance(data, (list, tuple)) or len(data) != len(batch):
                raise ValueError("embedding 响应数量不匹配")

            ordered_embeddings = [None] * len(batch)
            seen_indices = set()
            for item in data:
                index = getattr(item, "index", None)
                if (
                    isinstance(index, bool)
                    or not isinstance(index, int)
                    or index < 0
                    or index >= len(batch)
                    or index in seen_indices
                ):
                    raise ValueError("embedding 响应索引无效")
                try:
                    embedding = item.embedding
                except AttributeError as exc:
                    raise ValueError("embedding 响应条目无效") from exc
                ordered_embeddings[index] = embedding
                seen_indices.add(index)

            if len(seen_indices) != len(batch):
                raise ValueError("embedding 响应索引不完整")
            all_embeddings.extend(ordered_embeddings)

        # 将结果映射回原始索引位置
        result = []
        embed_idx = 0
        for i, text in enumerate(texts):
            if text:
                result.append(all_embeddings[embed_idx])
                embed_idx += 1
            else:
                result.append([0.0] * self.dim)

        return result
