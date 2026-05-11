"""链路：检索 → 生成。

`ChatEngine` 是纯 Python 接口，通过回调（chunk / log / context）
向上层（Qt UI 或 CLI）汇报状态，不依赖 PySide6。
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Callable, Iterable, List, Optional, Sequence, TypedDict

from .logging_config import (
    configure_quiet_dependencies,
    patch_langchain_reviver_default,
)

configure_quiet_dependencies()
patch_langchain_reviver_default()

from langchain_core.documents import Document
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from .config import (
    AgentConfig,
    ChatModelConfig,
    env_flag,
    get_agent_config,
    get_chat_model_config,
)
from .deepseek_agent import DeepSeekToolAgent
from .persona import load_system_prompt, offline_response
from .rag import build_vector_store, format_context, retrieve_documents

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# LangGraph state
# --------------------------------------------------------------------------- #


class ChatState(TypedDict):
    """LangGraph 节点之间流转的状态。"""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: List[Document]


# 回调签名
LogFn = Callable[[str], None]
ChunkFn = Callable[[str], None]
SentenceFn = Callable[[str], None]


def _noop(_: str) -> None:  # pragma: no cover
    pass


# --------------------------------------------------------------------------- #
# Chat engine
# --------------------------------------------------------------------------- #


class ChatEngine:
    """整合 LLM、向量检索与持久化对话历史的对话引擎。

    所有副作用都通过传入回调暴露，方便 Qt 信号桥接和 CLI 流式打印。
    """

    # 跨实例复用 checkpointer，保证同一 thread_id 的多轮对话历史
    _memory = MemorySaver()

    def __init__(
        self,
        config: Optional[ChatModelConfig] = None,
        agent_config: Optional[AgentConfig] = None,
        log: LogFn = _noop,
    ) -> None:
        self.log = log
        self.config = config or get_chat_model_config()
        self.agent_config = agent_config or get_agent_config()
        self.llm: Optional[ChatOpenAI] = None
        if self.config.is_available:
            self.llm = ChatOpenAI(
                api_key=self.config.api_key,
                model=self.config.model,
                base_url=self.config.base_url,
                streaming=True,
            )
            self.log(f"初始化 LLM: {self.config.model}")
        else:
            self.log("未配置 LLM API key，将使用本地占位回复。")

        self.vector_store = build_vector_store()
        if self.vector_store is None:
            self.log("向量库不可用，将跳过 RAG 检索。")

        self.tool_agent: Optional[DeepSeekToolAgent] = None
        if self.config.is_available and self.agent_config.enable_tool_calls:
            try:
                self.tool_agent = DeepSeekToolAgent(
                    config=self.config,
                    agent_config=self.agent_config,
                    vector_store=self.vector_store,
                    log=self.log,
                )
                if self.tool_agent.enabled:
                    self.log("已启用 DeepSeek 多轮工具调用。")
            except Exception as e:
                self.log(f"DeepSeek 工具调用初始化失败，将使用普通 RAG: {e}")

        self.graph = self._build_graph()

    # --------------------------- workflow --------------------------- #

    def _build_graph(self):
        workflow = StateGraph(state_schema=ChatState)
        workflow.add_node("retrieve", self._node_retrieve)
        workflow.add_node("generate", self._node_generate)
        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "generate")
        workflow.add_edge("generate", END)
        return workflow.compile(checkpointer=self._memory)

    def _latest_user_query(self, state: ChatState) -> str:
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                return msg.content
        return ""

    def _node_retrieve(self, state: ChatState) -> dict:
        query = self._latest_user_query(state)
        if not query:
            return {"context": []}
        if self.vector_store is None:
            return {"context": []}
        top_k = self._top_k()
        docs = retrieve_documents(self.vector_store, query, top_k=top_k)
        self.log(f"检索到 {len(docs)} 篇相关文档。")
        return {"context": docs}

    @staticmethod
    def _top_k() -> int:
        import os

        try:
            return max(0, int(os.getenv("DIGITAL_LDY_TOP_K", "3")))
        except ValueError:
            return 3

    def _node_generate(self, state: ChatState) -> dict:
        context_text = format_context(state["context"])
        system_prompt = load_system_prompt()
        # 仅保留 Human/AI 历史，避免重复注入 system
        history = [
            m for m in state["messages"] if not isinstance(m, SystemMessage)
        ]
        messages: List[BaseMessage] = [
            SystemMessage(
                content=(
                    f"{system_prompt}\n\n上下文信息如下:\n{context_text}\n\n"
                    "请记住用户的话题并保持人物口吻。"
                )
            ),
            *history,
        ]

        # 流式回调由调用方在 stream() 中处理；
        # 这里负责把最终消息写入 graph state（供 checkpointer 持久化）。
        if self.llm is None:
            response = offline_response(
                self._latest_user_query(state), context_text
            )
            self._on_chunk(response)
            self._flush_sentence_buffer(force=True)
            return {"messages": [AIMessage(content=response)]}

        response_text = ""
        try:
            for chunk in self.llm.stream(messages):
                piece = chunk.content or ""
                if not piece:
                    continue
                response_text += piece
                self._on_chunk(piece)
                self._sentence_buffer += piece
                if any(p in piece for p in "。！？.!?"):
                    self._flush_sentence_buffer()
            self._flush_sentence_buffer(force=True)
        except Exception as e:
            self.log(f"LLM 生成时出错: {e}")
            response_text = response_text or f"生成回答时出错: {e}"

        # 可选：将 AI 回复写回向量库（默认关闭，防止污染检索）
        if (
            self.vector_store is not None
            and env_flag("DIGITAL_LDY_STORE_AI_RESPONSE", False)
            and response_text
        ):
            try:
                self.vector_store.add_texts(
                    texts=[response_text],
                    metadatas=[
                        {
                            "type": "ai_response",
                            "user_query": self._latest_user_query(state)[:200],
                        }
                    ],
                    ids=[f"ai_response_{uuid.uuid4().hex}"],
                )
            except Exception as e:
                self.log(f"存储 AI 回复时出错: {e}")

        return {"messages": [AIMessage(content=response_text)]}

    # --------------------------- public API --------------------------- #

    def stream(
        self,
        user_message: str,
        thread_id: str = "default",
        on_chunk: ChunkFn = _noop,
        on_sentence: SentenceFn = _noop,
    ) -> str:
        """以流式方式处理一条用户消息，返回完整回复字符串。

        Parameters
        ----------
        on_chunk    : 每收到 LLM 输出片段时触发（用于 UI 实时显示）
        on_sentence : 检测到句末标点时触发（用于按句送 TTS）
        """
        self._on_chunk = on_chunk or _noop
        self._on_sentence = on_sentence or _noop
        self._sentence_buffer = ""

        if self.tool_agent is not None and self.tool_agent.enabled:
            try:
                return self.tool_agent.stream(
                    user_message=user_message,
                    thread_id=thread_id,
                    system_prompt=self._build_agent_system_prompt(),
                    on_chunk=self._on_chunk,
                    on_sentence=self._on_sentence,
                )
            except Exception as e:
                self.log(f"DeepSeek 工具链出错，回退普通 RAG: {e}")
                self._sentence_buffer = ""

        config = {"configurable": {"thread_id": thread_id}}
        initial: ChatState = {
            "messages": [HumanMessage(content=user_message)],
            "context": [],
        }
        final_state = self.graph.invoke(initial, config)

        # 取最后一条 AIMessage 作为完整回复
        for msg in reversed(final_state["messages"]):
            if isinstance(msg, AIMessage):
                return msg.content
        return ""

    def _build_agent_system_prompt(self) -> str:
        base_prompt = load_system_prompt()
        return (
            f"{base_prompt}\n\n"
            "# 可用工具说明 #\n"
            "你可以调用 search_knowledge_base 在本地知识库中查找人物、情节、诗词、过往对话和风格样例。"
            "凡用户询问《红楼梦》情节、人物关系、诗词、林黛玉身世、潇湘馆生活，"
            "或你觉得需要更贴合原著与知识库材料时，应先调用此工具；普通寒暄可不调用。\n\n"
            "# 回答要求 #\n"
            "工具结果只作你的内在参照，不要像论文一样罗列来源。"
            "最终回复要像林黛玉自然开口：先有情绪与场景，再给回答；"
            "可点到诗意意象，但不要堆砌辞藻；可轻嗔、含蓄、敏感，却不要机械拒绝。"
        )

    def _flush_sentence_buffer(self, force: bool = False) -> None:
        text = self._sentence_buffer.strip()
        if not text:
            return
        if force or any(p in text for p in "。！？.!?"):
            self._on_sentence(text)
            self._sentence_buffer = ""
