"""GPT-SoVITS HTTP 客户端 + 服务器启动器。

上游仓库: https://github.com/RVC-Boss/GPT-SoVITS
本项目内置版本: GPT-SoVITS-v2-240821/。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from typing import Optional

import requests

from ..resources import get_resource
from .base import TTSClient, TTSError

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:9880/tts"
DEFAULT_REF_AUDIO = "resources/voice_ref.MP3"


def start_tts_server(
    project_dir: str = "GPT-SoVITS-v2-240821",
    timeout_s: int = 30,
) -> subprocess.Popen:
    """启动 GPT-SoVITS 的 api_v2.py 并等待端口就绪。"""
    gpt_sovits_dir = os.path.join(os.getcwd(), project_dir)
    process = subprocess.Popen(
        [sys.executable, "api_v2.py"],
        cwd=gpt_sovits_dir,
    )

    last_error: Optional[BaseException] = None
    for _ in range(timeout_s):
        try:
            resp = requests.get(DEFAULT_URL, timeout=2)
            # 200 / 400 都说明服务已经能响应
            if resp.status_code < 500:
                logger.info("GPT-SoVITS 启动成功 (status=%s)", resp.status_code)
                return process
        except requests.exceptions.RequestException as e:
            last_error = e
        time.sleep(1)

    process.terminate()
    raise TTSError(f"GPT-SoVITS 启动超时: {last_error}")


class GPTSoVITSClient(TTSClient):
    """本地 GPT-SoVITS HTTP 接口。"""

    def __init__(
        self,
        url: str = DEFAULT_URL,
        ref_audio: str = DEFAULT_REF_AUDIO,
        text_lang: str = "zh",
        prompt_lang: str = "zh",
    ) -> None:
        self.url = url
        self.ref_audio = os.path.abspath(get_resource(ref_audio))
        self.text_lang = text_lang
        self.prompt_lang = prompt_lang

    def synthesize(self, text: str) -> Optional[str]:
        params = {
            "text": text,
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio,
            "prompt_lang": self.prompt_lang,
            "text_split_method": "cut5",
            "streaming_mode": False,
            "batch_size": 1,
            "speed_factor": 1.0,
        }
        try:
            resp = requests.get(self.url, params=params, timeout=60)
        except requests.exceptions.RequestException as e:
            logger.warning("GPT-SoVITS 请求失败: %s", e)
            return None
        if resp.status_code != 200:
            logger.warning(
                "GPT-SoVITS 返回异常 %s: %s", resp.status_code, resp.text[:200]
            )
            return None
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(resp.content)
            return f.name
