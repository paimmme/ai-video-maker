"""
edge-tts 配音 + 逐词时间戳
"""
import asyncio
from pathlib import Path
import edge_tts
from edge_tts import SubMaker


async def gen_scene_audio(
    narration: str, voice: str, out_path: Path
) -> tuple[Path, str]:
    """生成单场景配音音频，返回 (音频路径, SRT字幕文本)."""
    communicate = edge_tts.Communicate(narration, voice)
    submaker = SubMaker()

    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    srt = submaker.get_srt()
    return out_path, srt.decode("utf-8") if isinstance(srt, bytes) else srt
