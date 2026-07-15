"""
配图获取: Pexels 搜图 / SiliconFlow AI 生图 / Placeholder 占位
"""
import io
from pathlib import Path
import httpx
from config import Config


async def _download(url: str, out_path: Path) -> bool:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        resp = await c.get(url)
        if resp.status_code != 200:
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
    return True


async def _pexels_search(api_key: str, query: str, locale: str) -> str | None:
    """Search Pexels for first photo URL. Returns original size URL or None."""
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 5, "locale": locale}

    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            return None
        data = resp.json()
        photos = data.get("photos", [])
        if not photos:
            return None
        # Prefer landscape photos
        for p in photos:
            w, h = p.get("width", 0), p.get("height", 0)
            if w >= h:  # landscape or square
                return p["src"].get("original") or p["src"].get("large")
        return photos[0]["src"].get("original") or photos[0]["src"].get("large")


async def _siliconflow_gen(api_key: str, model: str, prompt: str, out_path: Path) -> bool:
    """Generate image via SiliconFlow API (OpenAI-compatible)."""
    url = "https://api.siliconflow.cn/v1/images/generations"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "prompt": prompt + ", 横构图 16:9, 高清",
        "n": 1,
        "size": "1920x1080",
    }

    async with httpx.AsyncClient(timeout=120) as c:
        resp = await c.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            return False
        data = resp.json()
        img_url = data.get("data", [{}])[0].get("url")
        if not img_url:
            return False
        return await _download(img_url, out_path)


async def _placeholder_gen(prompt: str, out_path: Path, width: int, height: int) -> bool:
    """Generate colored placeholder image via FFmpeg."""
    import subprocess
    import random

    r, g, b = random.randint(30, 200), random.randint(30, 200), random.randint(30, 200)
    color = f"0x{r:02x}{g:02x}{b:02x}"

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:d=1",
        "-frames:v", "1",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


async def fetch_image(cfg: Config, visual_prompt: str, scene_id: int, out_dir: Path) -> Path:
    """
    Fetch one image for a scene. Returns path to saved image.
    Tries: Pexels → SiliconFlow → Placeholder
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"scene_{scene_id:03d}.jpg"

    # 1) Pexels
    if cfg.img_provider == "pexels" and cfg.pexels_api_key:
        url = await _pexels_search(cfg.pexels_api_key, visual_prompt, cfg.img_locale)
        if url and await _download(url, out_path):
            return out_path

    # 2) SiliconFlow
    if cfg.siliconflow_api_key:
        ok = await _siliconflow_gen(cfg.siliconflow_api_key, cfg.siliconflow_model, visual_prompt, out_path)
        if ok:
            return out_path

    # 3) Placeholder
    ok = await _placeholder_gen(visual_prompt, out_path, cfg.width, cfg.height)
    if ok:
        return out_path

    raise RuntimeError(f"所有图片源都失败了: scene {scene_id}, prompt={visual_prompt}")
