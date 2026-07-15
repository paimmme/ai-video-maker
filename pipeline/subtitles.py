"""
SRT 字幕处理: 合并多场景 SRT + 时间偏移
"""
import re
from pathlib import Path


_SRT_BLOCK = re.compile(
    r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\Z)",
    re.DOTALL,
)


def _srt_time_to_ms(t: str) -> int:
    """00:01:23,456 → 83456 ms"""
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)


def _ms_to_srt_time(ms: int) -> str:
    """83456 ms → 00:01:23,456"""
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(srt_text: str) -> list[dict]:
    """Parse SRT text into list of {index, start_ms, end_ms, text}."""
    entries = []
    for m in _SRT_BLOCK.finditer(srt_text):
        entries.append({
            "index": int(m.group(1)),
            "start_ms": _srt_time_to_ms(m.group(2)),
            "end_ms": _srt_time_to_ms(m.group(3)),
            "text": m.group(4).strip(),
        })
    return entries


def format_srt(entries: list[dict]) -> str:
    """Format entries back to SRT text."""
    lines = []
    for i, e in enumerate(entries, 1):
        lines.append(str(i))
        lines.append(f"{_ms_to_srt_time(e['start_ms'])} --> {_ms_to_srt_time(e['end_ms'])}")
        lines.append(e["text"])
        lines.append("")
    return "\n".join(lines)


def merge_scene_srts(scene_srts: list[str], scene_durations_ms: list[int]) -> str:
    """
    合并多个场景的 SRT，对每个场景的字幕时间偏移累计时长。
    scene_srts[i] = scene i 的原始 SRT 文本
    scene_durations_ms[i] = scene i 的音频时长（毫秒）
    """
    all_entries = []
    cumulative = 0

    for srt_text, dur_ms in zip(scene_srts, scene_durations_ms):
        entries = parse_srt(srt_text)
        for e in entries:
            e["start_ms"] += cumulative
            e["end_ms"] += cumulative
        all_entries.extend(entries)
        cumulative += dur_ms

    return format_srt(all_entries)


def write_srt(srt_text: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(srt_text, encoding="utf-8")
    return out_path
