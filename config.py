import os
from pathlib import Path
from typing import Optional
import yaml


DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class Config:
    def __init__(self, path: str | Path | None = None):
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))

        # LLM
        llm = raw.get("llm", {})
        self.llm_provider: str = llm.get("provider", "deepseek")
        self.llm_api_key: str = llm.get("api_key", "") or os.getenv("DEEPSEEK_API_KEY", "")
        self.llm_base_url: str = llm.get("base_url", "https://api.deepseek.com")
        self.llm_model: str = llm.get("model", "deepseek-chat")

        # TTS
        tts = raw.get("tts", {})
        self.tts_voice: str = tts.get("voice", "zh-CN-XiaoxiaoNeural")

        # Images
        img = raw.get("images", {})
        self.img_provider: str = img.get("provider", "placeholder")
        self.pexels_api_key: str = img.get("pexels_api_key", "") or os.getenv("PEXELS_API_KEY", "")
        self.siliconflow_api_key: str = img.get("siliconflow_api_key", "") or os.getenv("SILICONFLOW_API_KEY", "")
        self.siliconflow_model: str = img.get("siliconflow_model", "stabilityai/stable-diffusion-3-5-large")
        self.img_locale: str = img.get("locale", "zh-CN")

        # Video
        vid = raw.get("video", {})
        self.fps: int = vid.get("fps", 24)
        self.width: int = vid.get("width", 1920)
        self.height: int = vid.get("height", 1080)
        self.ken_burns_zoom: float = vid.get("ken_burns_zoom", 0.06)
        self.transition_duration: float = vid.get("transition_duration", 0.5)
        self.bgm_path: Optional[str] = vid.get("bgm_path") or None
        self.bgm_volume: float = vid.get("bgm_volume", 0.15)
