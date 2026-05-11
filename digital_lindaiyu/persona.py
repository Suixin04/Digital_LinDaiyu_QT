"""人物设定与离线兜底回复。"""

from __future__ import annotations

from functools import lru_cache

from .resources import read_text_resource

PROMPT_RESOURCE = r"resources\prompt.txt"


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    """惰性加载 prompt.txt，避免每轮重复读盘。"""
    return read_text_resource(PROMPT_RESOURCE)


def offline_response(user_message: str, context_text: str = "") -> str:
    """当 LLM 不可用时给出符合人物口吻的占位回复。"""
    if "林黛玉" in user_message or "介绍" in user_message:
        return (
            "我本姑苏林氏之女，幼失怙恃，蒙外祖母怜惜，寄居荣国府。"
            "素日不过以诗书遣怀，又因身世飘零，心中常有几分凄楚。"
            "你若问我心性，大约不过是多思、多病，也不肯把真情轻付俗人罢了。"
        )
    if context_text and context_text != "没有找到相关上下文。":
        return (
            "你这话倒牵着旧事。依我所记，不过是情真二字最难，"
            "若添了虚浮热闹，反叫人心冷。"
        )
    return (
        "你这话我已听见了。只是眼前可凭的旧文不多，"
        "我便只照自己的心意回你：凡事若失了真心，再热闹也不过是空的。"
    )
