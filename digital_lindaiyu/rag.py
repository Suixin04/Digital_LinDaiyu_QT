"""向量库构造与检索辅助。"""

from __future__ import annotations

import logging
from typing import List, Optional

from langchain_core.documents import Document

from .config import env_flag
from .embeddings import get_embeddings

logger = logging.getLogger(__name__)

VECTOR_DIR = "./knowledge_base"


def build_vector_store(persist_directory: str = VECTOR_DIR):
    """创建（或打开）持久化的 Chroma 向量库。

    若检索功能被关闭，或嵌入后端初始化失败，则返回 ``None``，
    上层调用方应将其视为“无可用知识库”。
    """
    if not env_flag("DIGITAL_LDY_ENABLE_RETRIEVAL", True):
        logger.info("DIGITAL_LDY_ENABLE_RETRIEVAL=false; 跳过知识库初始化。")
        return None

    try:
        from chromadb.config import Settings
        from langchain_chroma import Chroma

        embeddings = get_embeddings()
        return Chroma(
            persist_directory=persist_directory,
            embedding_function=embeddings,
            client_settings=Settings(
                anonymized_telemetry=False,
                is_persistent=True,
                chroma_product_telemetry_impl=(
                    "digital_lindaiyu.chroma_noop.NoopTelemetry"
                ),
                chroma_telemetry_impl=(
                    "digital_lindaiyu.chroma_noop.NoopTelemetry"
                ),
            ),
        )
    except Exception as e:
        logger.warning("初始化向量库失败，将以无知识库模式运行: %s", e)
        return None


def retrieve_documents(
    vector_store,
    query: str,
    top_k: int = 3,
) -> List[Document]:
    """对 query 做相似度检索，向量库不可用或检索失败时返回空列表。"""
    if vector_store is None or not query:
        return []
    try:
        return vector_store.similarity_search(query, k=top_k)
    except Exception as e:
        logger.warning("检索文档时出错: %s", e)
        return []


def format_context(docs: List[Document]) -> str:
    """将检索结果拼成 system prompt 所需的上下文字符串。"""
    if not docs:
        return "没有找到相关上下文。"
    return "\n".join(doc.page_content for doc in docs)
