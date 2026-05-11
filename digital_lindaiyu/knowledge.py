"""把本地 knowledge/ 目录中的资料加载进向量库。"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Dict

from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_community.document_loaders import (
    DirectoryLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import env_flag
from .embeddings import get_embeddings
from .rag import VECTOR_DIR

logger = logging.getLogger(__name__)


def _stable_id(source: str, chunk_index: int, content: str) -> str:
    """基于源文件、序号和内容哈希生成稳定 ID，便于增量更新。"""
    digest = hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()[:10]
    safe_source = source.replace("\\", "/")
    return f"{safe_source}::chunk_{chunk_index}::{digest}"


def _build_loaders(base_dirs: Dict[str, str]):
    loaders = {}
    for doc_type, dir_path in base_dirs.items():
        if not (os.path.exists(dir_path) and os.listdir(dir_path)):
            continue
        if doc_type == "txt":
            loaders[doc_type] = DirectoryLoader(
                dir_path,
                glob="**/*.txt",
                loader_cls=TextLoader,
                loader_kwargs={"encoding": "utf-8"},
            )
        elif doc_type == "pdf":
            loaders[doc_type] = DirectoryLoader(
                dir_path, glob="**/*.pdf", loader_cls=PyPDFLoader
            )
        elif doc_type == "md":
            loaders[doc_type] = DirectoryLoader(
                dir_path, glob="**/*.md", loader_cls=UnstructuredMarkdownLoader
            )
    return loaders


def load_knowledge_base(
    rebuild: bool | None = None,
    persist_directory: str = VECTOR_DIR,
) -> int:
    """加载 knowledge/ 中的文本到向量库。

    Parameters
    ----------
    rebuild : 是否先清空再写入；默认读取 ``DIGITAL_LDY_REBUILD_KB``。

    Returns 成功写入的 chunk 数量。
    """
    if rebuild is None:
        rebuild = env_flag("DIGITAL_LDY_REBUILD_KB", False)

    try:
        embeddings = get_embeddings()
    except Exception as e:
        logger.error("嵌入模型不可用，跳过知识库加载: %s", e)
        return 0

    settings = Settings(
        anonymized_telemetry=False,
        is_persistent=True,
        chroma_product_telemetry_impl=(
            "digital_lindaiyu.chroma_noop.NoopTelemetry"
        ),
        chroma_telemetry_impl="digital_lindaiyu.chroma_noop.NoopTelemetry",
    )
    vector_store = Chroma(
        persist_directory=persist_directory,
        embedding_function=embeddings,
        client_settings=settings,
    )

    if rebuild:
        try:
            vector_store.delete_collection()
            vector_store = Chroma(
                persist_directory=persist_directory,
                embedding_function=embeddings,
                client_settings=settings,
            )
            logger.info("已清空现有向量存储")
        except Exception as e:
            logger.info("清空向量存储时出错（首次运行可忽略）: %s", e)
    else:
        logger.info(
            "保留现有向量存储（增量模式）；如需重建，设 DIGITAL_LDY_REBUILD_KB=true。"
        )

    base_dirs = {
        "txt": "./knowledge/txt",
        "pdf": "./knowledge/pdf",
        "md": "./knowledge/md",
    }
    for dir_path in base_dirs.values():
        os.makedirs(dir_path, exist_ok=True)

    loaders = _build_loaders(base_dirs)
    documents = []
    for doc_type, loader in loaders.items():
        try:
            docs = loader.load()
            logger.info("已加载 %s 文件 %d 篇", doc_type, len(docs))
            documents.extend(docs)
        except Exception as e:
            logger.warning("加载 %s 文档时出错: %s", doc_type, e)

    if not documents:
        logger.warning("没有成功加载任何文档")
        return 0

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?"],
    )
    splits = splitter.split_documents(documents)
    logger.info("文档分割完成，共 %d 块", len(splits))
    if not splits:
        return 0

    # 给每个源文件分配独立的 chunk 计数器，避免 ID 冲突
    per_source_index: Dict[str, int] = {}
    total_added = 0
    batch_size = 50

    for i in range(0, len(splits), batch_size):
        batch = splits[i : i + batch_size]
        ids, texts, metadatas = [], [], []
        for doc in batch:
            source = doc.metadata.get("source", "unknown")
            chunk_idx = per_source_index.get(source, 0)
            per_source_index[source] = chunk_idx + 1
            ids.append(_stable_id(source, chunk_idx, doc.page_content))
            texts.append(doc.page_content)
            metadatas.append(doc.metadata)
        try:
            vector_store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
            total_added += len(batch)
        except Exception as e:
            logger.warning("批量添加失败 %s；改为逐条添加", e)
            for text, meta, _id in zip(texts, metadatas, ids):
                try:
                    vector_store.add_texts(
                        texts=[text], metadatas=[meta], ids=[_id]
                    )
                    total_added += 1
                except Exception as inner:
                    logger.warning("单条添加失败: %s", inner)

    logger.info("向量存储更新完成，新增 %d 块", total_added)
    return total_added
