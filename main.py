"""
ai-video-maker CLI — 从文案生成 16:9 横屏视频，直发 Bilibili

用法:
  python main.py generate 文案.txt
  python main.py generate 文案.txt --config myconfig.yaml --bgm bgm.mp3
"""
import asyncio
import sys
from pathlib import Path
import click

from config import Config
from pipeline.planner import plan_scenes
from pipeline.tts import gen_scene_audio
from pipeline.images import fetch_image
from pipeline.subtitles import merge_scene_srts, write_srt
from pipeline.composer import compose


@click.group()
def cli():
    pass


@cli.command()
@click.argument("script_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--config", "-c", default=None, help="配置文件路径，默认使用 config.yaml")
@click.option("--output", "-o", default="output", help="输出目录")
@click.option("--bgm", "-b", default=None, help="背景音乐文件路径")
@click.option("--skip-llm", is_flag=True, help="跳过 LLM 拆解，直接使用文案全文作为单场景")
def generate(script_file, config, output, bgm, skip_llm):
    """从文案生成完整视频"""
    asyncio.run(_generate(script_file, config, output, bgm, skip_llm))


async def _generate(script_file, config, output, bgm, skip_llm):
    cfg = Config(config) if config else Config()
    if bgm:
        cfg.bgm_path = bgm

    script_text = Path(script_file).read_text(encoding="utf-8")
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    click.echo("=== 1/5 文案拆解分镜 ===")
    scenes = plan_scenes(cfg, script_text)
    if skip_llm or not scenes:
        scenes = [{"scene_id": 1, "narration": script_text, "visual_prompt": "", "duration_sec": 30}]
    click.echo(f"   → {len(scenes)} 个场景")

    audio_dir = out_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    img_dir = out_dir / "images"
    img_dir.mkdir(exist_ok=True)

    # Step 2+3: 并行 TTS + 配图
    click.echo("=== 2/5 生成配音 ===")
    audio_paths = []
    scene_srts = []
    for i, scene in enumerate(scenes):
        click.echo(f"   scene {i+1}: {scene['narration'][:50]}...")
        aud_path = audio_dir / f"scene_{i:03d}.mp3"
        aud_path, srt = await gen_scene_audio(scene["narration"], cfg.tts_voice, aud_path)
        audio_paths.append(aud_path)
        scene_srts.append(srt)

    click.echo("=== 3/5 获取配图 ===")
    image_paths = []
    for i, scene in enumerate(scenes):
        prompt = scene.get("visual_prompt", "") or scene["narration"][:30]
        click.echo(f"   scene {i+1}: \"{prompt}\"")
        try:
            img_path = await fetch_image(cfg, prompt, i + 1, img_dir)
            image_paths.append(img_path)
        except RuntimeError as e:
            click.echo(f"   ⚠️ {e}", err=True)
            click.echo("   使用纯色占位图替代", err=True)
            # Generate a minimal placeholder via ImageMagick fallback
            placeholder = img_dir / f"scene_{i+1:03d}.jpg"
            from pipeline.images import _placeholder_gen
            ok = await _placeholder_gen(prompt, placeholder, cfg.width, cfg.height)
            if not ok:
                raise
            image_paths.append(placeholder)

    # Step 4: 合并字幕
    click.echo("=== 4/5 生成字幕 ===")
    scene_durations_ms = []
    for aud_p in audio_paths:
        from pipeline.composer import _ffprobe_duration
        dur_sec = _ffprobe_duration(aud_p)
        scene_durations_ms.append(int(dur_sec * 1000))

    combined_srt = merge_scene_srts(scene_srts, scene_durations_ms)
    srt_path = out_dir / "subtitles.srt"
    write_srt(combined_srt, srt_path)
    click.echo(f"   → {srt_path}")

    # Step 5: 合成
    click.echo("=== 5/5 视频合成 ===")
    final = compose(cfg, scenes, audio_paths, image_paths, srt_path, out_dir / "video")
    click.echo(f"\n✅ 完成: {final}")
    click.echo(f"   {final.stat().st_size / 1024 / 1024:.1f} MB")


@cli.command()
def list_voices():
    """列出可用的 edge-tts 中文语音"""
    import edge_tts
    voices = asyncio.run(edge_tts.list_voices())
    for v in voices:
        if v["Locale"].startswith("zh"):
            click.echo(f"{v['ShortName']:30s} {v['Gender']:4s} {v['Locale']}")


@cli.command()
@click.argument("text")
@click.option("--voice", default="zh-CN-XiaoxiaoNeural")
@click.option("--output", "-o", default="test_tts.mp3")
def test_tts(text, voice, output):
    """测试 TTS 效果 (同步)"""
    async def _run():
        from pipeline.tts import gen_scene_audio
        return await gen_scene_audio(text, voice, Path(output))
    p, srt = asyncio.run(_run())
    print(f"音频: {p}")
    print(f"字幕:\n{srt[:500]}")


if __name__ == "__main__":
    cli()
