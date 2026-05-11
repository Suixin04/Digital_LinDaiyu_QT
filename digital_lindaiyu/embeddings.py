"""可插拔的嵌入模型后端。

- DashScope: 云端 text-embedding-v3 / v2（高质量，需 API key）
- FastEmbed: 本地 ONNX 模型（默认 BGE-small-zh-v1.5，无需 key）

通过 ``get_embeddings()`` 工厂统一获取 langchain `Embeddings` 实现。
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import List, Optional

from langchain_core.embeddings import Embeddings

from .config import (
    EmbeddingConfig,
    get_dashscope_api_key,
    get_dashscope_base_url,
    get_embedding_config,
)


# --------------------------------------------------------------------------- #
# DashScope 后端
# --------------------------------------------------------------------------- #


_DASHSCOPE_MAX_BATCH = 25


class DashScopeEmbeddings(Embeddings):
    """通过官方 dashscope SDK 调用 text-embedding 系列模型。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-v3",
        base_url: Optional[str] = None,
    ) -> None:
        import dashscope  # 延迟导入

        self._dashscope = dashscope
        self.model = model
        self.api_key = api_key or get_dashscope_api_key()
        if not self.api_key:
            raise RuntimeError("未设置 DASHSCOPE_API_KEY，无法使用 DashScope 嵌入。")
        dashscope.api_key = self.api_key
        # base_url 仅在使用 OpenAI 兼容接口时有意义，这里保留作配置项
        self.base_url = base_url or get_dashscope_base_url()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), _DASHSCOPE_MAX_BATCH):
            batch = texts[i : i + _DASHSCOPE_MAX_BATCH]
            resp = self._dashscope.TextEmbedding.call(
                model=self.model,
                input=batch,
                api_key=self.api_key,
            )
            if resp.status_code != HTTPStatus.OK:
                raise RuntimeError(f"DashScope 嵌入失败: {resp}")
            for emb in resp.output["embeddings"]:
                out.append(emb["embedding"])
        return out

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


# --------------------------------------------------------------------------- #
# 本地 FastEmbed 后端
# --------------------------------------------------------------------------- #


class FastEmbedEmbeddings(Embeddings):
    """fastembed 本地 ONNX 模型；首次使用会自动下载权重。"""

    def __init__(self, model: str = "BAAI/bge-small-zh-v1.5") -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "未安装 fastembed。运行: uv pip install fastembed"
            ) from e
        cache_dir = os.getenv("FASTEMBED_CACHE_DIR")
        self._model = TextEmbedding(model_name=model, cache_dir=cache_dir)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # fastembed 返回 numpy 数组；显式转成原生 float list，
        # 以避免下游（Chroma）对 np.float32 标量校验失败。
        return [vec.tolist() for vec in self._model.embed(texts)]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


# --------------------------------------------------------------------------- #
# 工厂
# --------------------------------------------------------------------------- #


def get_embeddings(config: Optional[EmbeddingConfig] = None) -> Embeddings:
    """根据配置返回合适的 Embeddings 实例。"""
    cfg = config or get_embedding_config()
    if cfg.backend == "dashscope":
        return DashScopeEmbeddings(model=cfg.model)
    if cfg.backend == "fastembed":
        return FastEmbedEmbeddings(model=cfg.model)
    raise ValueError(f"未知的嵌入后端: {cfg.backend}")
