"""Small helpers for splitting streamed text into speakable sentences."""

from __future__ import annotations

_SENTENCE_ENDS = set("。！？.!?\n")
_CLOSERS = set("”’\"')）]］】》」』")
_BRACKET_OPEN_TO_CLOSE = {
    "(": ")",
    "（": "）",
    "[": "]",
    "［": "］",
    "【": "】",
}
_BRACKET_CLOSES = set(_BRACKET_OPEN_TO_CLOSE.values())


def pop_speakable_sentences(
    buffer: str,
    force: bool = False,
) -> tuple[list[str], str]:
    """Return complete sentences and the remaining incomplete tail."""
    sentences: list[str] = []
    start = 0
    index = 0
    length = len(buffer)
    bracket_stack: list[str] = []
    while index < length:
        ch = buffer[index]
        if ch in _BRACKET_OPEN_TO_CLOSE:
            bracket_stack.append(_BRACKET_OPEN_TO_CLOSE[ch])
            index += 1
            continue
        if bracket_stack:
            if ch == bracket_stack[-1]:
                bracket_stack.pop()
            elif ch in _BRACKET_OPEN_TO_CLOSE:
                bracket_stack.append(_BRACKET_OPEN_TO_CLOSE[ch])
            elif ch in _BRACKET_CLOSES:
                bracket_stack.pop()
            index += 1
            continue
        if ch in _BRACKET_CLOSES:
            index += 1
            continue
        if ch not in _SENTENCE_ENDS:
            index += 1
            continue
        end = index + 1
        while end < length and buffer[end] in _CLOSERS:
            end += 1
        sentence = buffer[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = end
        index = end

    rest = buffer[start:]
    if force and rest.strip():
        sentences.append(rest.strip())
        rest = ""
    return sentences, rest
