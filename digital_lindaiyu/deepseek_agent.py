"""DeepSeek native multi-turn tool-call loop."""

from __future__ import annotations

import json
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


@dataclass
class StreamedAssistantMessage:
    message: dict[str, Any]
    finish_reason: str | None = None
    pending_sentence: str = ""


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
        result = self._run_tool_loop(turn_messages, on_chunk, on_sentence)
        # Store history without the per-turn system message.
        self.histories[thread_id] = result.messages[1:]
        return result.content

    # -------------------------- tool loop -------------------------- #

    def _run_tool_loop(
        self,
        messages: list[dict[str, Any]],
        on_chunk: ChunkFn,
        on_sentence: SentenceFn,
    ) -> AgentTurnResult:
        tools = available_tools(self.vector_store)
        made_tool_call = False
        for sub_turn in range(1, self.agent_config.max_tool_rounds + 1):
            if made_tool_call:
                self.log("工具结果已返回，继续请求模型。")
            streamed = self._stream_assistant_message(
                messages,
                tools=tools,
                on_chunk=on_chunk,
                on_sentence=on_sentence,
            )
            message = streamed.message

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                message = self._continue_if_truncated(
                    messages=messages,
                    message=message,
                    finish_reason=streamed.finish_reason,
                    pending_sentence=streamed.pending_sentence,
                    on_chunk=on_chunk,
                    on_sentence=on_sentence,
                )
                messages.append(message)
                content = str(message.get("content") or "").strip()
                return AgentTurnResult(content=content, messages=messages)

            messages.append(message)
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
        streamed = self._stream_assistant_message(
            final_messages,
            tools=[],
            on_chunk=on_chunk,
            on_sentence=on_sentence,
        )
        message = self._continue_if_truncated(
            messages=final_messages,
            message=streamed.message,
            finish_reason=streamed.finish_reason,
            pending_sentence=streamed.pending_sentence,
            on_chunk=on_chunk,
            on_sentence=on_sentence,
        )
        messages.extend(final_messages[len(messages) :])
        messages.append(message)
        return AgentTurnResult(
            content=str(message.get("content") or "").strip(), messages=messages
        )

    def _stream_assistant_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_chunk: ChunkFn,
        on_sentence: SentenceFn,
        initial_sentence_buffer: str = "",
    ) -> StreamedAssistantMessage:
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if self.agent_config.enable_thinking:
            kwargs["reasoning_effort"] = self.agent_config.reasoning_effort
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        try:
            return self._consume_stream(
                kwargs, on_chunk, on_sentence, initial_sentence_buffer
            )
        except Exception:
            if not self.agent_config.enable_thinking:
                raise
            kwargs.pop("reasoning_effort", None)
            kwargs.pop("extra_body", None)
            self.log("当前模型未接受 thinking 参数，已自动关闭思考参数重试。")
            return self._consume_stream(
                kwargs, on_chunk, on_sentence, initial_sentence_buffer
            )

    def _continue_if_truncated(
        self,
        messages: list[dict[str, Any]],
        message: dict[str, Any],
        finish_reason: str | None,
        pending_sentence: str,
        on_chunk: ChunkFn,
        on_sentence: SentenceFn,
    ) -> dict[str, Any]:
        combined = dict(message)
        combined_content = str(combined.get("content") or "")
        combined_reasoning = str(combined.get("reasoning_content") or "")

        for _ in range(2):
            if finish_reason != "length":
                break
            self.log("模型输出触及长度限制，已自动请求续写。")
            continuation_messages = [
                *messages,
                combined,
                {
                    "role": "user",
                    "content": "请从刚才中断处自然接着说，不要重复已经说过的内容。",
                },
            ]
            streamed = self._stream_assistant_message(
                continuation_messages,
                tools=[],
                on_chunk=on_chunk,
                on_sentence=on_sentence,
                initial_sentence_buffer=pending_sentence,
            )
            continuation = streamed.message
            next_content = str(continuation.get("content") or "")
            if not next_content:
                break
            combined_content += next_content
            combined["content"] = combined_content
            next_reasoning = str(continuation.get("reasoning_content") or "")
            if next_reasoning:
                combined_reasoning += next_reasoning
                combined["reasoning_content"] = combined_reasoning
            finish_reason = streamed.finish_reason
            pending_sentence = streamed.pending_sentence

        if pending_sentence.strip() and finish_reason == "length":
            on_sentence(pending_sentence.strip())
        return _json_safe(combined)

    def _consume_stream(
        self,
        kwargs: dict[str, Any],
        on_chunk: ChunkFn,
        on_sentence: SentenceFn,
        initial_sentence_buffer: str = "",
    ) -> StreamedAssistantMessage:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_call_parts: dict[int, dict[str, Any]] = {}
        sentence_buffer = initial_sentence_buffer
        finish_reason: str | None = None

        response = self.client.chat.completions.create(**kwargs)
        for chunk in response:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            finish_reason = _choice_get(choice, "finish_reason") or finish_reason
            delta = _choice_get(choice, "delta")
            if delta is None:
                continue

            reasoning_piece = _delta_get(delta, "reasoning_content")
            if reasoning_piece:
                reasoning_parts.append(str(reasoning_piece))

            piece = _delta_get(delta, "content")
            if piece:
                text_piece = str(piece)
                content_parts.append(text_piece)
                on_chunk(text_piece)
                sentence_buffer += text_piece
                if any(p in text_piece for p in "。！？.!?\n"):
                    flushed = sentence_buffer.strip()
                    if flushed:
                        on_sentence(flushed)
                    sentence_buffer = ""

            for tool_call in _delta_tool_calls(delta):
                _merge_tool_call_delta(tool_call_parts, tool_call)

        pending_sentence = sentence_buffer if finish_reason == "length" else ""
        flushed = sentence_buffer.strip()
        if flushed and finish_reason != "length":
            on_sentence(flushed)

        content = "".join(content_parts)
        message: dict[str, Any] = {"role": "assistant"}
        if content:
            message["content"] = content
        reasoning_content = "".join(reasoning_parts)
        if reasoning_content:
            message["reasoning_content"] = reasoning_content
        tool_calls = _assembled_tool_calls(tool_call_parts)
        if tool_calls:
            message["tool_calls"] = tool_calls
            message.setdefault("content", None)
        else:
            message.setdefault("content", content)
        return StreamedAssistantMessage(
            message=_json_safe(message),
            finish_reason=finish_reason,
            pending_sentence=pending_sentence,
        )


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


def _delta_get(delta, name: str):
    if isinstance(delta, dict):
        return delta.get(name)
    return getattr(delta, name, None)


def _choice_get(choice, name: str):
    if isinstance(choice, dict):
        return choice.get(name)
    return getattr(choice, name, None)


def _delta_tool_calls(delta) -> list[Any]:
    tool_calls = _delta_get(delta, "tool_calls")
    return list(tool_calls or [])


def _tool_call_get(tool_call, name: str):
    if isinstance(tool_call, dict):
        return tool_call.get(name)
    return getattr(tool_call, name, None)


def _function_get(function, name: str):
    if function is None:
        return None
    if isinstance(function, dict):
        return function.get(name)
    return getattr(function, name, None)


def _merge_tool_call_delta(
    tool_call_parts: dict[int, dict[str, Any]],
    tool_call,
) -> None:
    index = _tool_call_get(tool_call, "index")
    if index is None:
        index = len(tool_call_parts)
    index = int(index)

    target = tool_call_parts.setdefault(
        index,
        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
    )
    call_id = _tool_call_get(tool_call, "id")
    if call_id:
        target["id"] = str(call_id)
    call_type = _tool_call_get(tool_call, "type")
    if call_type:
        target["type"] = str(call_type)

    function = _tool_call_get(tool_call, "function")
    name_piece = _function_get(function, "name")
    if name_piece:
        target["function"]["name"] += str(name_piece)
    arguments_piece = _function_get(function, "arguments")
    if arguments_piece:
        target["function"]["arguments"] += str(arguments_piece)


def _assembled_tool_calls(
    tool_call_parts: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for index in sorted(tool_call_parts):
        tool_call = tool_call_parts[index]
        if not tool_call.get("id"):
            tool_call["id"] = f"tool_call_{index}"
        tool_calls.append(tool_call)
    return tool_calls
