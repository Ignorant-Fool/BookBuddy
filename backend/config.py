"""
BookBuddy — 全局配置

所有敏感信息通过环境变量 / .env 管理，不硬编码到代码里。
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

# ---------------------------------------------------------------- 路径
BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent

if load_dotenv is not None:
    for _env in (ROOT_DIR / ".env", BACKEND_DIR / ".env"):
        if _env.exists():
            load_dotenv(_env, override=False)

DATA_DIR = BACKEND_DIR / "data"
KB_DIR = DATA_DIR / "kb"
LOG_DIR = DATA_DIR / "logs"
UPLOAD_DIR = ROOT_DIR / "uploads"
SESSIONS_FILE = DATA_DIR / "sessions.json"
MODEL_CACHE_FILE = DATA_DIR / "model_cache.json"

for _d in (DATA_DIR, KB_DIR, LOG_DIR, UPLOAD_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# matplotlib 默认把字体缓存写到用户目录，沙箱/受限环境下可能无权限，统一放到项目内
MPL_DIR = DATA_DIR / "mpl"
MPL_DIR.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(MPL_DIR)

# ---------------------------------------------------------------- 阿里云百炼 DashScope
DASHSCOPE_API_KEY = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
if not DASHSCOPE_API_KEY:
    raise RuntimeError(
        "未设置 DASHSCOPE_API_KEY。\n"
        "请在项目根目录的 .env 文件中配置，例如：\n"
        "    DASHSCOPE_API_KEY=sk-xxxxxxxx\n"
        "可参考 .env.example 模板。"
    )

# OpenAI 兼容模式（Chat / Embedding）
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
).rstrip("/")
# 原生 DashScope（Rerank / ASR 多模态）
DASHSCOPE_NATIVE_URL = os.getenv(
    "DASHSCOPE_NATIVE_URL", "https://dashscope.aliyuncs.com/api/v1"
).rstrip("/")
RERANK_URL = f"{DASHSCOPE_NATIVE_URL}/services/rerank/text-rerank/text-rerank"
MULTIMODAL_URL = f"{DASHSCOPE_NATIVE_URL}/services/aigc/multimodal-generation/generation"

# ---------------------------------------------------------------- 模型（自动选择，可被 .env 覆盖）
# 每个角色给出一组候选，启动时按顺序挑第一个真实可用的模型。
MODEL_CANDIDATES: dict[str, list[str]] = {
    # 复杂推理 / Agent 规划：追求效果
    "agent": ["qwen3.8-max", "qwen3.7-max", "qwen-max", "qwen3.7-plus", "qwen-plus"],
    # 常规问答合成
    "chat": ["qwen3.7-plus", "qwen3.6-plus", "qwen3.8-max", "qwen-plus", "qwen-max", "qwen3.7-flash"],
    # 简单问题：追求速度
    "fast": ["qwen3.7-flash", "qwen3.6-flash", "qwen-flash", "qwen-turbo", "qwen3.7-plus"],
    # 向量化
    "embedding": ["qwen3.7-text-embedding", "text-embedding-v4", "qwen3.7-text-embedding-flash"],
    # 精排
    "rerank": ["qwen3.7-text-rerank", "qwen3-rerank", "gte-rerank-v2", "gte-rerank"],
    # 语音识别（原生多模态接口）
    "asr": [
        "qwen3-asr-flash",
        "qwen3-asr-flash-realtime",
        "qwen-audio-3.0-asr-flash",
        "fun-asr-flash-2026-06-15",
        "fun-asr-flash",
    ],
}

# .env 中对具体角色的显式覆盖
ROLE_ENV_OVERRIDE = {
    "agent": "AGENT_MODEL",
    "chat": "LLM_MODEL",
    "fast": "FAST_MODEL",
    "embedding": "EMBED_MODEL",
    "rerank": "RERANK_MODEL",
    "asr": "ASR_MODEL",
}

# 是否启用模型"思考模式"。默认关闭：
# 百炼 qwen3.x 默认先输出 reasoning_content，思考过程会吃掉 max_tokens，
# 导致 content 为空。关闭后更快、更稳定；想要更强推理可设为 1。
ENABLE_THINKING = (os.getenv("ENABLE_THINKING", "0").strip() in ("1", "true", "True"))

# ---------------------------------------------------------------- 知识库
ALLOWED_UPLOAD_EXT = {".txt", ".md", ".docx", ".doc", ".pptx", ".ppt", ".pdf"}
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
MIN_CHUNK_CHARS = 50
RETRIEVE_TOP_K = int(os.getenv("RETRIEVE_TOP_K", "20"))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "8"))
RERANK_MIN_SCORE = float(os.getenv("RERANK_MIN_SCORE", "0.10"))

# ---------------------------------------------------------------- Agent
MAX_RETRIEVAL_ROUNDS = int(os.getenv("MAX_RETRIEVAL_ROUNDS", "2"))
MAX_REFINE_ROUNDS = int(os.getenv("MAX_REFINE_ROUNDS", "2"))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "20"))
MAX_SESSIONS = 50

# ---------------------------------------------------------------- 音频
SAMPLE_RATE = 16000
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
AUDIO_EXTS = {".wav", ".mp3", ".webm", ".m4a", ".ogg", ".flac", ".aac", ".mp4"}
