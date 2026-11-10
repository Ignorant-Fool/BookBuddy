"""
端到端冒烟测试（需要后端已启动在 http://127.0.0.1:5000）

    ..\.venv\Scripts\python.exe tests\smoke_test.py [--skip-upload] [--book 红楼梦]

覆盖：健康检查 → 知识库上传/统计/预览 → 文本问答 → 语音问答 → 人物关系
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:5000"
ROOT = Path(__file__).resolve().parent.parent
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"  [{PASS if ok else FAIL}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 58 - len(title)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--doc", default="红楼梦-第一至三回.txt", help="test_docs/ 下的测试文档")
    parser.add_argument("--audio", default="林黛玉是谁.mp3")
    parser.add_argument("--question", default="林黛玉第一次出场是第几回？")
    args = parser.parse_args()

    # ---------------- 1. 健康检查
    section("1. 健康检查")
    try:
        health = requests.get(f"{BASE}/api/health", timeout=60).json()
    except Exception as exc:
        check("后端可达", False, str(exc))
        print("\n请先启动后端：start-backend.bat")
        return 1
    check("后端可达", health.get("status") == "ok")
    print("      模型:", json.dumps(health.get("models", {}), ensure_ascii=False))

    # ---------------- 2. 知识库
    section("2. 知识库")
    stats = requests.get(f"{BASE}/api/kb/stats", timeout=60).json()["stats"]
    print(f"      当前: {stats['source_count']} 文件 / {stats['total_chunks']} 片段")

    if not args.skip_upload:
        doc = ROOT / "test_docs" / args.doc
        if not doc.exists():
            check(f"测试文档存在", False, str(doc))
        else:
            started = time.perf_counter()
            with doc.open("rb") as handle:
                resp = requests.post(
                    f"{BASE}/api/kb/upload",
                    files={"file": (doc.name, handle, "text/plain")},
                    timeout=1800,
                ).json()
            elapsed = round(time.perf_counter() - started, 1)
            ok = bool(resp.get("success")) and any(r.get("status") == "ok" for r in resp.get("results", []))
            detail = json.dumps(resp.get("results", [{}])[0], ensure_ascii=False)
            check(f"上传《{doc.name}》({elapsed}s)", ok, detail)

    stats = requests.get(f"{BASE}/api/kb/stats", timeout=60).json()["stats"]
    check("知识库非空", stats["total_chunks"] > 0, f"{stats['total_chunks']} 片段 / {stats['source_count']} 文件")

    if stats["sources"]:
        source = stats["sources"][0]
        preview = requests.get(f"{BASE}/api/kb/preview", params={"source": source}, timeout=120).json()
        check("片段预览", len(preview.get("content", "")) > 0, f"{len(preview.get('content', ''))} 字符")

    # ---------------- 3. 文本问答
    section("3. 文本问答（Agentic RAG）")
    started = time.perf_counter()
    answer = requests.post(
        f"{BASE}/api/send-text",
        json={"text": args.question, "session_id": "smoke_text"},
        timeout=600,
    ).json()
    elapsed = round(time.perf_counter() - started, 1)
    ok = bool(answer.get("success")) and bool(answer.get("llm_answer"))
    check(f"回答生成 ({elapsed}s, model={answer.get('model')})", ok)
    if ok:
        print("      问题:", args.question)
        print("      回答:", answer["llm_answer"][:400].replace("\n", " "))
        print("      步骤:")
        for step in answer.get("agent_steps", []):
            print(f"        · [{step['type']}] {step['content'][:110]}")

    # ---------------- 4. 语音问答
    section("4. 语音问答（ASR + Agentic RAG）")
    audio = ROOT / "test_audio" / args.audio
    if audio.exists():
        started = time.perf_counter()
        with audio.open("rb") as handle:
            voice = requests.post(
                f"{BASE}/api/process-audio",
                files={"audio": (audio.name, handle, "audio/mpeg")},
                data={"session_id": "smoke_voice"},
                timeout=900,
            ).json()
        elapsed = round(time.perf_counter() - started, 1)
        ok = bool(voice.get("success"))
        check(f"语音处理 ({elapsed}s)", ok, voice.get("error", ""))
        if ok:
            print("      音频:", args.audio, f"({voice.get('duration')}s)")
            print("      ASR :", voice.get("asr_text"), f"[{voice.get('asr_model')}]")
            print("      波形图:", len(voice.get("waveform_image", "")), "字节(base64)")
            print("      MFCC  :", voice.get("mfcc_shape"))
            print("      回答 :", (voice.get("llm_answer") or "")[:300].replace("\n", " "))
    else:
        check("测试音频存在", False, str(audio))

    # ---------------- 5. 人物关系
    section("5. 人物关系抽取")
    started = time.perf_counter()
    chars = requests.post(
        f"{BASE}/api/kb/characters", json={"query": "林黛玉"}, timeout=600
    ).json()
    elapsed = round(time.perf_counter() - started, 1)
    ok = bool(chars.get("success")) and bool(chars.get("data", {}).get("characters"))
    check(f"人物抽取 ({elapsed}s)", ok, chars.get("error", ""))
    if ok:
        for item in chars["data"]["characters"][:6]:
            print(f"      · {item.get('name')}: {item.get('relation') or item.get('relations') or ''}")

    # ---------------- 汇总
    section("结果汇总")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, _ in results:
        print(f"  {'✓' if ok else '✗'} {name}")
    print(f"\n  {passed}/{total} 通过")
    return 0 if passed == total else 2


if __name__ == "__main__":
    sys.exit(main())
