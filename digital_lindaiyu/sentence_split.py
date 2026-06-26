"""Small helpers for splitting streamed text into speakable sentences."""

from __future__ import annotations

_SENTENCE_ENDS = set("。！？.!?\n")
_CLOSERS = set("”’\"')）】》」』")


def pop_speakable_sentences(
    buffer: str,
    force: bool = False,
) -> tuple[list[str], str]:
    """Return complete sentences and the remaining incomplete tail."""
    sentences: list[str] = []
    start = 0
    index = 0
    length = len(buffer)
    while index < length:
        if buffer[index] not in _SENTENCE_ENDS:
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
