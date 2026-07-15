"""
edge-tts 配音 + 基于 SentenceBoundary 的 SRT 字幕
"""
import asyncio
import re
from pathlib import Path
import edge_tts
from edge_tts import SubMaker


async def gen_scene_audio(
    narration: str, voice: str, out_path: Path
) -> tuple[Path, str]:
    """生成单场景配音音频，返回 (音频路径, SRT字幕文本).

    edge-tts 中文语音不发 WordBoundary，只发 SentenceBoundary。
    字幕策略：按句切分 + 字符数等比分配总时长。
    """
    communicate = edge_tts.Communicate(narration, voice)

    # 收集所有音频 + SentenceBoundary
    audio_segments: list[bytes] = []
    sent_offsets_ms: list[int] = []  # 每句结尾的累积音频时长(毫秒)
    sent_boundary_text: list[str] = []

    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_segments.append(chunk["data"])
                f.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                sent_offsets_ms.append(chunk.get("offset", 0))  # Azure ticks or ms
                # edge-tts SubMaker internally also tracks text — use raw narration split instead

    audio_duration_ms = _estimate_duration_ms(out_path)

    # 按标点拆分句子（保留分隔符映射）
    sents = _split_sentences(narration)
    if not sents:
        sents = [narration]

    if len(sent_offsets_ms) == len(sents) and sent_offsets_ms[-1] > 0:
        # 用 SentenceBoundary 时间戳（转为毫秒，Azure ticks→ms）
        if sent_offsets_ms[-1] > audio_duration_ms * 2000:
            # 看起来是 Azure HNS ticks（100-ns 单位）
            sent_ends = [t // 10000 for t in sent_offsets_ms]
        else:
            sent_ends = sent_offsets_ms
        # 对齐长度
        while len(sent_ends) < len(sents):
            sent_ends.append(audio_duration_ms)
        sent_ends[-1] = audio_duration_ms
        sent_starts = [0] + sent_ends[:-1]
    else:
        # 回退：按字符数等比分配
        total_chars = sum(len(s) for s in sents)
        if total_chars == 0:
            total_chars = 1
        sent_starts = []
        sent_ends = []
        cum = 0.0
        for s in sents:
            ratio = len(s) / total_chars
            dur = int(audio_duration_ms * ratio)
            sent_starts.append(int(cum))
            cum += dur
            sent_ends.append(int(cum))

    # 生成 SRT
    lines = []
    idx = 1
    for i, s in enumerate(sents):
        if not s.strip():
            continue
        start = sent_starts[i]
        end = sent_ends[i]
        if end - start < 300:
            end = start + 300  # 最短 300ms
        lines.append(f"{idx}")
        lines.append(f"{_ms_to_srt(start)} --> {_ms_to_srt(end)}")
        lines.append(s.strip())
        lines.append("")
        idx += 1

    srt_text = "\n".join(lines)
    return out_path, srt_text


def _ms_to_srt(ms: int) -> str:
    """毫秒 → SRT 时间格式 00:01:23,456"""
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _estimate_duration_ms(audio_path: Path) -> int:
    """用 ffprobe 获取音频时长（毫秒）"""
    import subprocess, json
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(audio_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(r.stdout)
    return int(float(data["format"]["duration"]) * 1000)


def _split_sentences(text: str) -> list[str]:
    """按中文句末标点 + 换行切分句子，每个句组为一个 subtitle."""
    parts = re.split(r"(?<=[。！？\n])", text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return [text]
    # 如果句子很长（>30字），内部再按逗号/分号拆分
    result = []
    for p in parts:
        if len(p) > 30:
            sub = re.split(r"(?<=[，；、])", p)
            result.extend(s.strip() for s in sub if s.strip())
        else:
            result.append(p)
    return result
