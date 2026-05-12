"""GPT-SoVITS HTTP 客户端 + 服务器启动器。

上游：https://github.com/RVC-Boss/GPT-SoVITS
本地源码：``GPT-SoVITS/``，专用环境：``GPT-SoVITS/.venv-gsv``。

集成思路：
1. ``start_tts_server(cfg)`` 用专用环境启动 ``api_v2.py``，把 FFmpeg DLL
   目录 prepend 到子进程 PATH（torchcodec 依赖），并探测端口就绪。
2. 服务起来后通过 ``/set_gpt_weights`` 和 ``/set_sovits_weights``
   切到当前已训练的林黛玉模型。
3. 参考音如果是 MP3，启动时用项目内的 ffmpeg.exe 预转一份 WAV 缓存，
   避免推理时再依赖 torchcodec 解 MP3。
4. ``GPTSoVITSClient.synthesize(text)`` 按句调用 ``/tts``，
   配合 ``ChatEngine.stream(on_sentence=...)`` 实现"边生成边朗读"。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Optional

import requests

from ..config import GPTSoVITSConfig, get_gpt_sovits_config
from ..resources import get_resource
from .base import TTSClient, TTSError

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #


def _abs_under_project(cfg: GPTSoVITSConfig, rel_or_abs: str) -> str:
    """把可能是相对路径的字符串解析为绝对路径（基准：当前工作目录）。"""
    if os.path.isabs(rel_or_abs):
        return rel_or_abs
    return os.path.abspath(rel_or_abs)


def _server_alive(base_url: str, timeout: float = 2.0) -> bool:
    """探测 api_v2 是否能响应。

    api_v2 没有专门的健康检查端点，``/tts`` 无参时会返回 500，
    所以只要 HTTP 连接成功就视为就绪（任何状态码都可）。
    """
    try:
        requests.get(f"{base_url}/tts", timeout=timeout)
    except requests.exceptions.RequestException:
        return False
    return True


def _convert_to_wav_if_needed(src: str, cfg: GPTSoVITSConfig) -> str:
    """如果 ref 音频是 MP3 等格式，预先用 ffmpeg 转一份 16kHz WAV。

    转换结果放在 ``<项目根>/runtime/cache/ref_<basename>.wav``，
    便于排查；如果同名 WAV 已存在且比源新，则直接复用。
    """
    src = _abs_under_project(cfg, src)
    if not os.path.isfile(src):
        raise TTSError(f"参考音频不存在: {src}")

    if src.lower().endswith(".wav"):
        return src

    cache_dir = os.path.join(os.path.abspath("."), "runtime", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(src))[0]
    dst = os.path.join(cache_dir, f"ref_{base}.wav")

    if (
        os.path.isfile(dst)
        and os.path.getmtime(dst) >= os.path.getmtime(src)
    ):
        return dst

    # 解析 ffmpeg.exe 路径：优先 cfg.ffmpeg_bin，其次 PATH
    ffmpeg_exe = None
    if cfg.ffmpeg_bin:
        cand = os.path.join(
            cfg.ffmpeg_bin, "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        )
        if os.path.isfile(cand):
            ffmpeg_exe = cand
    if ffmpeg_exe is None:
        ffmpeg_exe = shutil.which("ffmpeg")
    if ffmpeg_exe is None:
        raise TTSError(
            "找不到 ffmpeg，无法把参考音频转换为 WAV。"
            "请把 ffmpeg.exe 放进 PATH 或设置 GPT_SOVITS_FFMPEG_BIN。"
        )

    logger.info("转换参考音频 %s -> %s", src, dst)
    subprocess.run(
        [
            ffmpeg_exe, "-y", "-i", src,
            "-ac", "1", "-ar", "32000",
            "-loglevel", "error",
            dst,
        ],
        check=True,
    )
    return dst


def _build_child_env(cfg: GPTSoVITSConfig) -> dict:
    """构造启动 api_v2 的子进程环境。"""
    env = os.environ.copy()
    if cfg.ffmpeg_bin and os.path.isdir(cfg.ffmpeg_bin):
        sep = os.pathsep
        env["PATH"] = cfg.ffmpeg_bin + sep + env.get("PATH", "")
    # 让 api_v2 看到 GPT-SoVITS 根作为 PYTHONPATH 顶部
    env["PYTHONPATH"] = (
        os.path.abspath(cfg.project_dir)
        + os.pathsep
        + env.get("PYTHONPATH", "")
    )
    return env


# --------------------------------------------------------------------------- #
# 启动 / 健康检查 / 模型切换
# --------------------------------------------------------------------------- #


def _wait_until_ready(
    base_url: str, timeout_s: int, proc: subprocess.Popen
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise TTSError(
                f"GPT-SoVITS api_v2 进程已退出，退出码 {proc.returncode}"
            )
        if _server_alive(base_url):
            return
        time.sleep(1.0)
    raise TTSError(f"GPT-SoVITS 启动超时 ({timeout_s}s)")


def _switch_weights(cfg: GPTSoVITSConfig) -> None:
    """加载训练好的林黛玉权重。"""
    for endpoint, path in (
        ("/set_gpt_weights", cfg.gpt_weights),
        ("/set_sovits_weights", cfg.sovits_weights),
    ):
        url = f"{cfg.base_url}{endpoint}"
        try:
            resp = requests.get(url, params={"weights_path": path}, timeout=120)
        except requests.exceptions.RequestException as e:
            raise TTSError(f"切换权重失败 ({endpoint}): {e}") from e
        if resp.status_code != 200:
            raise TTSError(
                f"切换权重失败 {endpoint}: HTTP {resp.status_code} {resp.text[:200]}"
            )
        logger.info("已加载权重 %s -> %s", endpoint, path)


def _warmup(cfg: GPTSoVITSConfig) -> None:
    """做一次极短的合成请求，预热模型 & CUDA 图，把首句冷启动开销提前付掉。"""
    try:
        client = GPTSoVITSClient(cfg=cfg)
        path = client.synthesize("嗯。")
        client.close()
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
            logger.info("GPT-SoVITS 预热完成")
    except Exception as e:  # noqa: BLE001
        logger.warning("GPT-SoVITS 预热失败（不影响正常使用）: %s", e)


def start_tts_server(
    cfg: Optional[GPTSoVITSConfig] = None,
) -> Optional[subprocess.Popen]:
    """启动 ``api_v2.py`` 并加载林黛玉权重。

    - 若 ``cfg.auto_start`` 为 False，直接尝试连接已运行的服务。
    - 若目标端口已在响应，则不重复启动，只切换权重。
    - 返回 Popen 对象（已运行的服务时返回 None）。
    """
    cfg = cfg or get_gpt_sovits_config()

    if _server_alive(cfg.base_url):
        logger.info("检测到已运行的 GPT-SoVITS 服务 %s", cfg.base_url)
        _switch_weights(cfg)
        return None

    if not cfg.auto_start:
        raise TTSError(
            f"GPT-SoVITS 服务 {cfg.base_url} 未运行，且 GPT_SOVITS_AUTO_START=0"
        )

    project_dir = os.path.abspath(cfg.project_dir)
    if not os.path.isdir(project_dir):
        raise TTSError(f"GPT-SoVITS 目录不存在: {project_dir}")
    if not os.path.isfile(cfg.python_exe):
        raise TTSError(f"Python 解释器不存在: {cfg.python_exe}")

    cmd = [
        cfg.python_exe,
        "api_v2.py",
        "-a", cfg.host,
        "-p", str(cfg.port),
        "-c", cfg.config_file,
    ]
    env = _build_child_env(cfg)
    logger.info("启动 GPT-SoVITS: %s (cwd=%s)", " ".join(cmd), project_dir)
    process = subprocess.Popen(cmd, cwd=project_dir, env=env)

    try:
        _wait_until_ready(cfg.base_url, cfg.startup_timeout, process)
        _switch_weights(cfg)
        _warmup(cfg)
    except Exception:
        process.terminate()
        raise

    logger.info("GPT-SoVITS 就绪 @ %s", cfg.base_url)
    return process


# --------------------------------------------------------------------------- #
# 客户端
# --------------------------------------------------------------------------- #


class GPTSoVITSClient(TTSClient):
    """调用本地 api_v2 ``/tts`` 合成单句语音。"""

    def __init__(self, cfg: Optional[GPTSoVITSConfig] = None) -> None:
        self.cfg = cfg or get_gpt_sovits_config()
        # 预先把 MP3 转 WAV，避开 api_v2 端 torchcodec 解 MP3 的潜在问题
        try:
            ref_path = _convert_to_wav_if_needed(self.cfg.ref_audio, self.cfg)
        except TTSError:
            # 转换失败就退回原路径，让 api_v2 自己处理
            logger.exception("参考音频预处理失败，使用原路径")
            ref_path = _abs_under_project(self.cfg, self.cfg.ref_audio)
        self.ref_audio = ref_path
        self._session = requests.Session()

    def synthesize(self, text: str) -> Optional[str]:
        text = (text or "").strip()
        if not text:
            return None
        payload = {
            "text": text,
            "text_lang": self.cfg.text_lang,
            "ref_audio_path": self.ref_audio,
            "prompt_text": self.cfg.prompt_text,
            "prompt_lang": self.cfg.prompt_lang,
            # 上层 ChatEngine 已按句切，禁用 api_v2 的二次切分以省一次扫描
            "text_split_method": "cut0",
            "batch_size": 1,
            "speed_factor": 1.0,
            # 采样参数：略调小可缩短解码时间，质量损失基本不可闻
            "top_k": 10,
            "top_p": 0.9,
            "temperature": 0.9,
            "parallel_infer": True,
            "streaming_mode": False,
            "media_type": "wav",
        }
        try:
            resp = self._session.post(
                f"{self.cfg.base_url}/tts", json=payload, timeout=120
            )
        except requests.exceptions.RequestException as e:
            logger.warning("GPT-SoVITS 请求失败: %s", e)
            return None
        if resp.status_code != 200:
            logger.warning(
                "GPT-SoVITS /tts 异常 %s: %s",
                resp.status_code, resp.text[:200],
            )
            return None
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(resp.content)
            return f.name

    def close(self) -> None:
        self._session.close()
