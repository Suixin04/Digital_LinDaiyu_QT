"""CLI 烟测：直接调用 ChatEngine，不依赖 Qt。

用法:
    uv run python -m scripts.test_chat "请介绍一下林黛玉"
"""

from __future__ import annotations

import sys

from digital_lindaiyu.logging_config import configure_app_logging

configure_app_logging()

from digital_lindaiyu.chat import ChatEngine


def main() -> int:
    user_message = (
        " ".join(sys.argv[1:]).strip()
        or "请介绍一下红楼梦中的林黛玉"
    )

    engine = ChatEngine(log=lambda m: print(f"[engine] {m}"))
    response = engine.stream(
        user_message,
        thread_id="cli",
        on_chunk=lambda s: print(s, end="", flush=True),
    )
    print("\n--- 完成 ---")
    print(f"完整回复: {response[:100]}{'...' if len(response) > 100 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
