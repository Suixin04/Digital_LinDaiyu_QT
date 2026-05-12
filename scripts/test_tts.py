"""一次性 TTS 集成冒烟测试。"""
import os
import shutil
import time

from digital_lindaiyu.config import get_gpt_sovits_config
from digital_lindaiyu.tts.gpt_sovits import GPTSoVITSClient, start_tts_server


def main() -> None:
    cfg = get_gpt_sovits_config()
    print("REF:", cfg.ref_audio)
    proc = start_tts_server(cfg)
    try:
        client = GPTSoVITSClient(cfg)
        print("REF_WAV:", client.ref_audio)
        for i, txt in enumerate(
            ["你好，我是林黛玉。", "哥哥的玉，是件稀罕物，怎么会人人都有呢。"]
        ):
            t0 = time.monotonic()
            path = client.synthesize(txt)
            dur = time.monotonic() - t0
            size = os.path.getsize(path) if path and os.path.isfile(path) else 0
            print(f"SYNTH{i+1} {dur:.2f}s -> {path} size={size}")
            if path and i == 1:
                out = os.path.abspath(
                    os.path.join("runtime", "cache", "sample_lindaiyu_demo.wav")
                )
                os.makedirs(os.path.dirname(out), exist_ok=True)
                shutil.copy(path, out)
                print("SAVED:", out)
    finally:
        if proc is not None:
            proc.terminate()


if __name__ == "__main__":
    main()
