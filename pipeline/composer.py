"""
FFmpeg 视频合成: Ken Burns 每场景视频片段 → 拼接 → 烧字幕 → BGM
"""
import subprocess
import json
from pathlib import Path
from config import Config


def _ffprobe_duration(path: Path) -> float:
    """Get media duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(r.stdout)
    return float(data["format"]["duration"])


def make_scene_clip(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
    zoom_amount: float,
) -> Path:
    """Create single scene clip: Ken Burns on image + narration audio."""
    audio_dur = _ffprobe_duration(audio_path)
    total_frames = max(int(audio_dur * fps), 1)
    zoom_per_frame = zoom_amount / total_frames if total_frames > 1 else 0

    vf = (
        f"zoompan="
        f"z='min(zoom+{zoom_per_frame:.6f},1+{zoom_amount})':"
        f"d={total_frames}:"
        f"s={width}x{height}:"
        f"fps={fps}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def _write_concat_file(clip_paths: list[Path], filelist_path: Path):
    """Write FFmpeg concat demuxer file list."""
    lines = []
    for p in clip_paths:
        lines.append(f"file '{p.resolve()}'")
    filelist_path.write_text("\n".join(lines), encoding="utf-8")


def concat_clips(clip_paths: list[Path], output_path: Path) -> Path:
    """Concatenate scene clips (no transition — direct cut)."""
    if len(clip_paths) == 1:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        clip_paths[0].rename(output_path)
        return output_path

    filelist = output_path.parent / "_concat.txt"
    _write_concat_file(clip_paths, filelist)

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(filelist),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    filelist.unlink(missing_ok=True)
    return output_path


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path) -> Path:
    """Burn SRT subtitles into video."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles={str(srt_path.resolve())}",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def add_bgm(video_path: Path, bgm_path: Path, bgm_volume: float, output_path: Path) -> Path:
    """Mix background music into video."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(bgm_path),
        "-filter_complex",
        f"[0:a]volume=1.0[a0];[1:a]volume={bgm_volume}[a1];"
        f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2",
        "-c:v", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def compose(
    cfg: Config,
    scene_data: list[dict],
    audio_paths: list[Path],
    image_paths: list[Path],
    combined_srt_path: Path,
    output_dir: Path,
) -> Path:
    """
    完整合成: 每场景 Ken Burns 片段 → 拼接 → 烧字幕 → (BGM).
    Returns final video path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(exist_ok=True)

    # Step 1: 生成每个场景的片段
    clip_paths = []
    for i, (img_p, aud_p) in enumerate(zip(image_paths, audio_paths)):
        clip_out = clips_dir / f"scene_{i:03d}.mp4"
        make_scene_clip(
            image_path=img_p,
            audio_path=aud_p,
            output_path=clip_out,
            width=cfg.width,
            height=cfg.height,
            fps=cfg.fps,
            zoom_amount=cfg.ken_burns_zoom,
        )
        clip_paths.append(clip_out)

    # Step 2: 拼接
    concat_path = output_dir / "_concat.mp4"
    concat_clips(clip_paths, concat_path)

    # Step 3: 烧字幕
    sub_path = output_dir / "_subtitled.mp4"
    burn_subtitles(concat_path, combined_srt_path, sub_path)

    # Step 4: BGM (可选)
    if cfg.bgm_path:
        bgm_path_obj = Path(cfg.bgm_path)
        if bgm_path_obj.exists():
            final_path = output_dir / "final_video.mp4"
            add_bgm(sub_path, bgm_path_obj, cfg.bgm_volume, final_path)
            # 清理中间件
            concat_path.unlink(missing_ok=True)
            sub_path.unlink(missing_ok=True)
            return final_path

    # 无 BGM，直接重命名
    final_path = output_dir / "final_video.mp4"
    sub_path.rename(final_path)
    concat_path.unlink(missing_ok=True)
    return final_path
