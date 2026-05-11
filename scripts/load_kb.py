"""CLI: 把 knowledge/ 加载到向量库。

用法:
    uv run python -m scripts.load_kb            # 增量
    uv run python -m scripts.load_kb --rebuild  # 清空重建
"""

from __future__ import annotations

import argparse
import sys

from digital_lindaiyu.logging_config import configure_app_logging

configure_app_logging()

from digital_lindaiyu.knowledge import load_knowledge_base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rebuild", action="store_true", help="先清空向量库再写入"
    )
    args = parser.parse_args()
    count = load_knowledge_base(rebuild=args.rebuild)
    print(f"共写入 {count} 个文本块到知识库。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
