"""
音频预处理流水线（信号处理核心环节）

    加载(16k 单声道) → 谱减法降噪 → 幅度归一化 → MFCC 特征提取
                     → 波形图 / MFCC 热力图（base64 PNG）

降噪与可视化都做了容错：任一环节失败不阻断 ASR。
"""
from __future__ import annotations

import base64
import io
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from config import SAMPLE_RATE

logger = logging.getLogger(__name__)

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.max_open_warning"] = 0

# 浏览器常见的容器格式，libsndfile 无法直接解码，需要 ffmpeg 帮忙
_FFMPEG_EXTS = {".webm", ".m4a", ".mp4", ".aac", ".opus", ".amr", ".wma"}
_ffmpeg_checked = False
_ffmpeg_path: str | None = None


def _find_ffmpeg() -> str | None:
    global _ffmpeg_checked, _ffmpeg_path
    if not _ffmpeg_checked:
        _ffmpeg_path = shutil.which("ffmpeg")
        _ffmpeg_checked = True
        if _ffmpeg_path:
            logger.info("检测到 ffmpeg: %s", _ffmpeg_path)
        else:
            logger.warning("未检测到 ffmpeg，webm/m4a 等容器格式可能无法解码")
    return _ffmpeg_path


def decodable_path(file_path: str | Path) -> tuple[str | Path, str | None]:
    """返回可被 libsndfile 读取的路径；必要时用 ffmpeg 转成 16k 单声道 wav。"""
    path = Path(file_path)
    if path.suffix.lower() not in _FFMPEG_EXTS:
        return path, None

    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return path, None

    tmp = Path(tempfile.gettempdir()) / f"bookbuddy_{path.stem}_{abs(hash(str(path))) % 10**6}.wav"
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(path),
             "-ac", "1", "-ar", str(SAMPLE_RATE), str(tmp)],
            check=True, capture_output=True, timeout=120,
        )
        return tmp, str(tmp)
    except Exception as exc:
        logger.warning("ffmpeg 转码失败: %s", exc)
        return path, None


def load_audio(file_path: str | Path) -> tuple[np.ndarray, int]:
    """加载音频，重采样到 16kHz 单声道。"""
    import librosa

    audio, _ = librosa.load(str(file_path), sr=SAMPLE_RATE, mono=True)
    if audio.size == 0:
        raise ValueError("音频为空或无法解码")
    return np.asarray(audio, dtype=np.float32), SAMPLE_RATE


def reduce_noise(audio: np.ndarray, sr: int) -> np.ndarray:
    """谱减法降噪（noisereduce）。"""
    try:
        import noisereduce as nr

        return nr.reduce_noise(y=audio, sr=sr, prop_decrease=0.8)
    except Exception as exc:
        logger.warning("降噪失败，使用原始音频: %s", exc)
        return audio


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    return audio / peak if peak > 0 else audio


def extract_mfcc(audio: np.ndarray, sr: int, n_mfcc: int = 13) -> np.ndarray:
    """MFCC 特征矩阵 (n_mfcc x frames)。"""
    import librosa

    return librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=n_mfcc)


def _fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def generate_waveform_plot(audio: np.ndarray, sr: int) -> str:
    time = np.linspace(0, len(audio) / sr, len(audio), endpoint=False)
    fig, ax = plt.subplots(figsize=(10, 2))
    ax.plot(time, audio, color="#1e80ff", linewidth=0.5)
    ax.set_xlabel("时间 (s)")
    ax.set_ylabel("幅度")
    ax.set_title("音频波形图")
    if len(time) > 0:
        ax.set_xlim(0, float(time[-1]) or 1.0)
    ax.grid(True, alpha=0.3)
    return _fig_to_base64(fig)


def generate_mfcc_plot(mfcc: np.ndarray, sr: int) -> str:
    fig, ax = plt.subplots(figsize=(10, 3))
    img = ax.imshow(mfcc, origin="lower", aspect="auto", cmap="viridis")
    ax.set_xlabel("帧")
    ax.set_ylabel("MFCC 系数")
    ax.set_title("MFCC 特征热力图")
    fig.colorbar(img, ax=ax, format="%+2.0f dB")
    return _fig_to_base64(fig)


def process_audio_pipeline(file_path: str | Path) -> dict:
    """完整预处理流水线。"""
    decoded, cleanup = decodable_path(file_path)
    try:
        audio, sr = load_audio(decoded)
    finally:
        if cleanup:
            Path(cleanup).unlink(missing_ok=True)

    denoised = reduce_noise(audio, sr)
    normalized = normalize_audio(denoised)

    try:
        mfcc = extract_mfcc(normalized, sr)
        mfcc_image = generate_mfcc_plot(mfcc, sr)
        mfcc_shape = [int(mfcc.shape[0]), int(mfcc.shape[1])]
    except Exception as exc:
        logger.warning("MFCC 提取失败: %s", exc)
        mfcc_image, mfcc_shape = "", [0, 0]

    try:
        waveform_image = generate_waveform_plot(normalized, sr)
    except Exception as exc:
        logger.warning("波形图生成失败: %s", exc)
        waveform_image = ""

    return {
        "original_duration": round(len(audio) / sr, 2),
        "sample_rate": sr,
        "waveform_image": waveform_image,
        "mfcc_image": mfcc_image,
        "mfcc_shape": mfcc_shape,
        "normalized_audio": normalized,
    }
