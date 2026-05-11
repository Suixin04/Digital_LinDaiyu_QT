"""DeepSeek tool-calling functions backed by the local knowledge base."""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.documents import Document

from .rag import retrieve_documents


SEARCH_KNOWLEDGE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": (
            "在本地《红楼梦》/林黛玉知识库中检索相关资料。"
            "当用户询问人物关系、诗词、情节、身份、过往对话或需要更贴合原著口吻时使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用于检索的中文问题或关键词。",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回片段数量，默认 3，最多 6。",
                    "minimum": 1,
                    "maximum": 6,
                },
            },
            "required": ["query"],
        },
    },
}


def available_tools(vector_store) -> list[dict[str, Any]]:
    """Return tools available for the current runtime."""
    if vector_store is None:
        return []
    return [SEARCH_KNOWLEDGE_TOOL]


def run_tool(name: str, arguments: dict[str, Any], vector_store) -> str:
    """Run a tool call and return a JSON string for the model."""
    if name == "search_knowledge_base":
        return _search_knowledge_base(arguments, vector_store)
    return json.dumps(
        {"ok": False, "error": f"未知工具: {name}"}, ensure_ascii=False
    )


def _search_knowledge_base(arguments: dict[str, Any], vector_store) -> str:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return json.dumps(
            {"ok": False, "error": "query 不能为空"}, ensure_ascii=False
        )
    try:
        top_k = int(arguments.get("top_k") or os.getenv("DIGITAL_LDY_TOP_K", "3"))
    except (TypeError, ValueError):
        top_k = 3
    top_k = max(1, min(6, top_k))

    docs = retrieve_documents(vector_store, query, top_k=top_k)
    return json.dumps(
        {
            "ok": True,
            "query": query,
            "count": len(docs),
            "results": [_doc_to_payload(doc, i + 1) for i, doc in enumerate(docs)],
        },
        ensure_ascii=False,
    )


def _doc_to_payload(doc: Document, rank: int) -> dict[str, Any]:
    source = str(doc.metadata.get("source") or "unknown").replace("\\", "/")
    text = _compact_text(doc.page_content, max_chars=760)
    return {"rank": rank, "source": source, "text": text}


def _compact_text(text: str, max_chars: int) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= max_chars:
        return one_line
    return one_line[: max_chars - 1].rstrip() + "…"
