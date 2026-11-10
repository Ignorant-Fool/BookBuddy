"""
语音识别 —— 阿里云百炼 qwen3-asr-flash（原生多模态接口）。

接口：
    POST https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation
    {"model": "qwen3-asr-flash",
     "input": {"messages": [{"role": "user", "content": [{"audio": "data:audio/wav;base64,..."}]}]}}

模型自动选择：按候选顺序逐个尝试，把可用的模型缓存到 data/asr_model.json，
后续请求直接用缓存的模型，避免每次都试错。
"""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import requests

from config import DATA_DIR, DASHSCOPE_API_KEY, MODEL_CANDIDATES, MULTIMODAL_URL
from models import registry

logger = logging.getLogger(__name__)

MODEL_CACHE = DATA_DIR / "asr_model.json"
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 单次识别上限 10MB
TIMEOUT = 120

_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".amr": "audio/amr",
}


def _candidate_models() -> list[str]:
    """候选模型顺序：缓存优先 → MODEL_CANDIDATES 顺序。

    注意：/models 列表里虽然有 qwen-audio-3.0-asr-flash，但它在本网关下需要额外的
    format 参数，实际不可用；因此这里严格按 ASR 专用候选的顺序试，成功即缓存。
    """
    order: list[str] = []
    try:
        if MODEL_CACHE.exists():
            cached = json.loads(MODEL_CACHE.read_text(encoding="utf-8")).get("model")
            if cached:
                order.append(str(cached))
    except Exception:
        pass

    for model in MODEL_CANDIDATES.get("asr", []):
        if model not in order:
            order.append(model)
    return order


def _remember(model: str) -> None:
    try:
        MODEL_CACHE.write_text(json.dumps({"model": model}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _call(model: str, mime: str, audio_b64: str) -> dict:
    payload = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"audio": f"data:{mime};base64,{audio_b64}"}],
                }
            ]
        },
        "parameters": {"result_format": "message"},
    }
    resp = requests.post(
        MULTIMODAL_URL,
        headers={
            "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} {resp.text[:300]}")
    return resp.json()


def _parse(payload: dict) -> dict:
    output = payload.get("output") or {}
    choices = output.get("choices") or []
    if not choices:
        return {"text": "", "language": "", "emotion": ""}

    message = choices[0].get("message") or {}
    content = message.get("content") or []
    texts: list[str] = []
    if isinstance(content, str):
        texts.append(content)
    else:
        for part in content:
            if isinstance(part, dict) and part.get("text"):
                texts.append(str(part["text"]))
            elif isinstance(part, str):
                texts.append(part)

    language = ""
    emotion = ""
    for note in message.get("annotations") or []:
        if note.get("type") == "audio_info":
            language = str(note.get("language") or "")
            emotion = str(note.get("emotion") or "")

    return {"text": "".join(texts).strip(), "language": language, "emotion": emotion}


def transcribe_file(file_path: str | Path) -> dict:
    """语音文件 → 文本。返回 {text, confidence, language, model}。"""
    path = Path(file_path)
    raw = path.read_bytes()
    if not raw:
        raise ValueError("音频文件为空")
    if len(raw) > MAX_AUDIO_BYTES:
        raise ValueError(
            f"音频文件 {len(raw) / 1024 / 1024:.1f}MB 超过单次识别上限 10MB，请缩短录音时长"
        )

    mime = _MIME.get(path.suffix.lower(), "audio/wav")
    audio_b64 = base64.b64encode(raw).decode()

    errors: list[str] = []
    for model in _candidate_models():
        try:
            payload = _call(model, mime, audio_b64)
            parsed = _parse(payload)
            if parsed["text"]:
                _remember(model)
                registry.override("asr", model)
                return {
                    "text": parsed["text"],
                    "confidence": 0.92,
                    "language": parsed["language"],
                    "model": model,
                }
            errors.append(f"{model}: 返回空文本")
        except Exception as exc:  # 换下一个候选模型
            logger.warning("ASR 模型 %s 失败: %s", model, exc)
            errors.append(f"{model}: {exc}")

    raise RuntimeError("语音识别失败，所有候选模型均不可用。\n" + "\n".join(errors))
