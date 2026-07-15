"""
LLM 文案拆解 → 分镜列表
"""
import json
from typing import Any
from openai import OpenAI

from config import Config

SYSTEM_PROMPT = """你是一个视频脚本策划。把用户提供的文案拆分成适合视频制作的场景列表。

每个场景包含：
- narration: 该场景的旁白文本（1-3句话）
- visual_prompt: 画面描述关键词（用于搜索配图，简洁准确的中文关键词）
- duration_sec: 建议时长（秒，根据旁白字数估算，念完约每字0.2-0.3秒）

输出严格 JSON 数组（不要 markdown 包裹）：
[
  {"scene_id": 1, "narration": "...", "visual_prompt": "...", "duration_sec": 8.0}
]

规则：
- 每个场景旁白控制在 5-20 秒
- visual_prompt 是简洁中文关键词，用于搜图
- 视频比例为 16:9 横屏
- 所有字段用中文"""


def plan_scenes(cfg: Config, script_text: str) -> list[dict[str, Any]]:
    client = OpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)

    resp = client.chat.completions.create(
        model=cfg.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请为以下文案规划分镜：\n\n{script_text}"},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    text = resp.choices[0].message.content or "[]"
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    data = json.loads(text)
    scenes = data if isinstance(data, list) else data.get("scenes", data.get("results", []))

    for s in scenes:
        s.setdefault("scene_id", scenes.index(s) + 1)
        s.setdefault("duration_sec", 8.0)

    return scenes
