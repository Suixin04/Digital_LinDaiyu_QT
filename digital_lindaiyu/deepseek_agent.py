"""DeepSeek native multi-turn tool-call loop."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from openai import OpenAI

from .agent_tools import available_tools, run_tool
from .config import AgentConfig, ChatModelConfig

LogFn = Callable[[str], None]
ChunkFn = Callable[[str], None]
SentenceFn = Callable[[str], None]


@dataclass
class AgentTurnResult:
    content: str
    messages: list[dict[str, Any]]


class DeepSeekToolAgent:
    """Use DeepSeek's OpenAI-compatible tool calling with local tools."""

    def __init__(
        self,
        config: ChatModelConfig,
        agent_config: AgentConfig,
        vector_store,
        log: LogFn,
    ) -> None:
        self.config = config
        self.agent_config = agent_config
        self.vector_store = vector_store
        self.log = log
        self.client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        self.histories: dict[str, list[dict[str, Any]]] = {}

    @property
    def enabled(self) -> bool:
        return (
            self.config.is_available
            and self.agent_config.enable_tool_calls
            and bool(available_tools(self.vector_store))
        )

    def stream(
        self,
        user_message: str,
        thread_id: str,
        system_prompt: str,
        on_chunk: ChunkFn,
        on_sentence: SentenceFn,
    ) -> str:
        history = self.histories.setdefault(thread_id, [])
        turn_messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": user_message},
        ]
        result = self._run_tool_loop(turn_messages)
        # Store history without the per-turn system message.
        self.histories[thread_id] = result.messages[1:]
        self._emit_text(result.content, on_chunk, on_sentence)
        return result.content

    # -------------------------- tool loop -------------------------- #

    def _run_tool_loop(self, messages: list[dict[str, Any]]) -> AgentTurnResult:
        tools = available_tools(self.vector_store)
        made_tool_call = False
        for sub_turn in range(1, self.agent_config.max_tool_rounds + 1):
            response = self._create(messages, tools=tools)
            message = _message_to_dict(response.choices[0].message)
            messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                content = str(message.get("content") or "").strip()
                if made_tool_call:
                    self.log("工具调用完成，正在生成最终回复。")
                return AgentTurnResult(content=content, messages=messages)

            made_tool_call = True
            self.log(f"DeepSeek 请求工具调用（第 {sub_turn} 轮，共 {len(tool_calls)} 个）。")
            for tool_call in tool_calls:
                tool_name, arguments = _extract_tool_call(tool_call)
                short_query = str(arguments.get("query") or "")[:40]
                if short_query:
                    self.log(f"调用工具: {tool_name}({short_query}...)")
                else:
                    self.log(f"调用工具: {tool_name}")
                tool_result = run_tool(tool_name, arguments, self.vector_store)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "content": tool_result,
                    }
                )

        self.log("工具调用达到最大轮数，要求模型基于已有工具结果作答。")
        final_messages = [
            *messages,
            {
                "role": "user",
                "content": "请基于以上工具结果，直接以林黛玉的口吻给出最终回复。",
            },
        ]
        response = self._create(final_messages, tools=[])
        message = _message_to_dict(response.choices[0].message)
        messages.extend(final_messages[len(messages) :])
        messages.append(message)
        return AgentTurnResult(
            content=str(message.get("content") or "").strip(), messages=messages
        )

    def _create(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]):
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if self.agent_config.enable_thinking:
            kwargs["reasoning_effort"] = self.agent_config.reasoning_effort
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        try:
            return self.client.chat.completions.create(**kwargs)
        except Exception:
            if not self.agent_config.enable_thinking:
                raise
            kwargs.pop("reasoning_effort", None)
            kwargs.pop("extra_body", None)
            self.log("当前模型未接受 thinking 参数，已自动关闭思考参数重试。")
            return self.client.chat.completions.create(**kwargs)

    # -------------------------- output -------------------------- #

    def _emit_text(
        self,
        text: str,
        on_chunk: ChunkFn,
        on_sentence: SentenceFn,
    ) -> None:
        sentence_buffer = ""
        for piece in _chunk_for_display(text):
            on_chunk(piece)
            sentence_buffer += piece
            if any(p in piece for p in "。！？.!?\n"):
                flushed = sentence_buffer.strip()
                if flushed:
                    on_sentence(flushed)
                sentence_buffer = ""
            if self.agent_config.stream_delay_ms > 0:
                time.sleep(self.agent_config.stream_delay_ms / 1000)
        flushed = sentence_buffer.strip()
        if flushed:
            on_sentence(flushed)


def _message_to_dict(message) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        data = message.model_dump(exclude_none=True)
    else:
        data = dict(message)
    # DeepSeek's reasoning_content is an extra field. Preserve it if the SDK exposes it.
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning and "reasoning_content" not in data:
        data["reasoning_content"] = reasoning
    return _json_safe(data)


def _extract_tool_call(tool_call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function = tool_call.get("function") or {}
    name = str(function.get("name") or "")
    raw_args = function.get("arguments") or "{}"
    if isinstance(raw_args, dict):
        return name, raw_args
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError:
        args = {}
    return name, args


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(exclude_none=True))
    return value


def _chunk_for_display(text: str) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。！？.!?\n，、；;：:" or len(buf) >= 4:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks
