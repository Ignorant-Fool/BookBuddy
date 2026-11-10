"""
BookBuddy 后端入口 —— Flask + LangChain + LangGraph

接口：
    GET    /api/health              健康检查
    GET    /api/models              当前自动选中的模型
    POST   /api/kb/upload           上传文档 → 提取 → 切片 → 向量化
    GET    /api/kb/stats            知识库统计
    GET    /api/kb/preview          预览某个文件的完整切片
    DELETE /api/kb/delete-source    删除单个文件
    DELETE /api/kb/clear            清空知识库
    POST   /api/kb/characters       人物关系抽取
    POST   /api/process-audio       语音 → ASR → Agentic RAG
    POST   /api/send-text           文本 → Agentic RAG
"""
from __future__ import annotations

import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from characters import extract_characters
from config import (
    ALLOWED_UPLOAD_EXT,
    LOG_DIR,
    MAX_CONTENT_LENGTH,
    ROOT_DIR,
    UPLOAD_DIR,
)
from graph import run_agent
from knowledge.store import knowledge_base
from memory import session_store
from models import registry, warm_up
from speech.asr import transcribe_file
from speech.cleaner import clean_text
from speech.preprocess import process_audio_pipeline

# ================================================================ 日志
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / f"app_{datetime.now():%Y%m%d}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("bookbuddy")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["JSON_AS_ASCII"] = False
CORS(app)

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


def _safe_name(name: str) -> str:
    """保留中文，只去掉路径分隔符与非法字符。"""
    name = (name or "").replace("\\", "/").split("/")[-1]
    for ch in '<>:"|?*\x00':
        name = name.replace(ch, "_")
    return name.strip() or "upload"


@app.errorhandler(413)
def too_large(_):
    return jsonify({"success": False, "error": "文件超过 50MB 上限"}), 413


# ================================================================ 基础接口
@app.route("/api/health", methods=["GET"])
def health():
    stats = knowledge_base.stats()
    return jsonify({
        "status": "ok",
        "service": "BookBuddy",
        "engine": "LangChain + LangGraph",
        "knowledge_base": stats,
        "sessions": session_store.count(),
        "models": registry.describe()["resolved"],
    })


@app.route("/api/models", methods=["GET"])
def models_info():
    return jsonify({"success": True, "data": registry.describe()})


@app.route("/api/models/refresh", methods=["POST"])
def models_refresh():
    registry.refresh(force=True)
    resolved = registry.resolve_all()
    return jsonify({"success": True, "data": resolved})


# ================================================================ 知识库
@app.route("/api/kb/upload", methods=["POST"])
def kb_upload():
    """上传文件到知识库：提取文本 → 语义切片 → 向量化 → 混合索引。"""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "未找到文件"}), 400

    files = request.files.getlist("file")
    results = []

    for file in files:
        if not file.filename:
            continue

        source_name = _safe_name(file.filename)
        ext = Path(source_name).suffix.lower()
        if ext not in ALLOWED_UPLOAD_EXT:
            results.append({"file": source_name, "error": f"不支持的格式 {ext}"})
            continue

        tmp_path = UPLOAD_DIR / f"kb_{os.getpid()}_{int(time.time() * 1000)}_{source_name}"
        try:
            file.save(str(tmp_path))
            info = knowledge_base.add_file(tmp_path, source_name=source_name)
            info["status"] = "ok"
            results.append(info)
        except Exception as exc:
            logger.exception("知识库上传失败: %s", source_name)
            results.append({"file": source_name, "error": str(exc)})
        finally:
            tmp_path.unlink(missing_ok=True)

    ok = sum(1 for r in results if r.get("status") == "ok")
    logger.info("[KB_UPLOAD] 文件 %d 个，成功 %d 个", len(files), ok)
    return jsonify({"success": True, "results": results})


@app.route("/api/kb/stats", methods=["GET"])
def kb_stats():
    return jsonify({"success": True, "stats": knowledge_base.stats()})


@app.route("/api/kb/preview", methods=["GET"])
def kb_preview():
    source = request.args.get("source", "")
    if not source:
        return jsonify({"success": False, "error": "缺少 source 参数"}), 400
    return jsonify({"success": True, "source": source, "content": knowledge_base.preview(source)})


@app.route("/api/kb/delete-source", methods=["DELETE"])
def kb_delete_source():
    source = request.args.get("source", "")
    if not source:
        return jsonify({"success": False, "error": "缺少 source 参数"}), 400
    knowledge_base.delete_source(source)
    logger.info("[KB_DELETE] %s", source)
    return jsonify({"success": True, "message": f"已删除 {source}"})


@app.route("/api/kb/clear", methods=["DELETE"])
def kb_clear():
    knowledge_base.clear()
    logger.info("[KB_CLEAR]")
    return jsonify({"success": True, "message": "知识库已清空"})


@app.route("/api/kb/characters", methods=["POST"])
def kb_characters():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    try:
        payload = extract_characters(query)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("人物关系抽取失败")
        return jsonify({"success": False, "error": str(exc)}), 500

    if not payload.get("characters"):
        return jsonify({"success": False, "error": "未能从知识库中提取到人物信息"}), 200
    return jsonify({"success": True, "data": payload})


# ================================================================ 问答
@app.route("/api/send-text", methods=["POST"])
def send_text():
    """文本 → Agentic RAG。"""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    session_id = data.get("session_id") or "default"

    if not text:
        return jsonify({"success": False, "error": "文本为空"}), 400

    history = session_store.history(session_id)
    started = time.perf_counter()

    result = run_agent(text, history)
    answer = result["answer"]

    session_store.append_turn(session_id, text, answer)
    elapsed = round(time.perf_counter() - started, 2)

    refused = result.get("refused") or ("暂无相关信息" in answer) or ("知识库为空" in answer)
    logger.info(
        "[AGENTIC] session=%s elapsed=%ss steps=%d model=%s refused=%s query=%s",
        session_id, elapsed, len(result["steps"]), result.get("model"), refused, text[:50],
    )

    return jsonify({
        "success": True,
        "cleaned_text": text,
        "llm_answer": answer,
        "asr_confidence": 1.0,
        "agent_steps": result["steps"],
        "model": result.get("model", ""),
        "evidence_count": result.get("evidence_count", 0),
        "elapsed": elapsed,
        "refused": bool(refused),
    })


@app.route("/api/process-audio", methods=["POST"])
def process_audio():
    """语音 → 预处理 → ASR → 清洗 → Agentic RAG。"""
    if "audio" not in request.files:
        return jsonify({"success": False, "error": "未找到音频文件"}), 400

    file = request.files["audio"]
    session_id = request.form.get("session_id", "default")
    if not file.filename:
        return jsonify({"success": False, "error": "文件名为空"}), 400

    ext = Path(file.filename).suffix or ".wav"
    tmp_path = UPLOAD_DIR / f"audio_{os.getpid()}_{int(time.time() * 1000)}{ext}"

    try:
        file.save(str(tmp_path))
        started = time.perf_counter()

        audio_result = process_audio_pipeline(tmp_path)
        asr_result = transcribe_file(tmp_path)
        cleaned = clean_text(asr_result["text"])

        answer = ""
        steps: list[dict] = []
        model = ""
        if cleaned:
            history = session_store.history(session_id)
            agent_result = run_agent(cleaned, history)
            answer = agent_result["answer"]
            steps = agent_result["steps"]
            model = agent_result.get("model", "")
            session_store.append_turn(session_id, cleaned, answer)

        elapsed = round(time.perf_counter() - started, 2)
        logger.info(
            "[AUDIO] session=%s duration=%ss elapsed=%ss asr=%s",
            session_id, audio_result["original_duration"], elapsed,
            (asr_result["text"] or "")[:40],
        )

        return jsonify({
            "success": True,
            "duration": audio_result["original_duration"],
            "waveform_image": audio_result["waveform_image"],
            "mfcc_image": audio_result["mfcc_image"],
            "mfcc_shape": audio_result["mfcc_shape"],
            "asr_text": asr_result["text"],
            "asr_confidence": asr_result["confidence"],
            "asr_model": asr_result.get("model", ""),
            "cleaned_text": cleaned,
            "llm_answer": answer,
            "agent_steps": steps,
            "model": model,
            "elapsed": elapsed,
        })

    except Exception as exc:
        logger.error("语音处理失败: %s\n%s", exc, traceback.format_exc())
        return jsonify({"success": False, "error": str(exc)}), 500
    finally:
        tmp_path.unlink(missing_ok=True)


# ================================================================ 前端静态资源（可选）
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path: str):
    if not FRONTEND_DIST.exists():
        return jsonify({
            "service": "BookBuddy API",
            "hint": "前端未构建。开发模式请运行 frontend 的 npm run dev（http://localhost:3000）",
            "api": [str(rule) for rule in app.url_map.iter_rules() if str(rule).startswith("/api")],
        })
    target = FRONTEND_DIST / path
    if path and target.exists():
        return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, "index.html")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 62)
    print("  BookBuddy · 阅读小助手  (LangChain + LangGraph)")
    print("=" * 62)

    warm_up()
    resolved = registry.resolve_all()
    for role, name in resolved.items():
        print(f"  {role:<10} → {name}")
    stats = knowledge_base.stats()
    print(f"  知识库     → {stats['source_count']} 个文件 / {stats['total_chunks']} 个片段")
    print("=" * 62)
    print("  API: http://127.0.0.1:5000")

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
