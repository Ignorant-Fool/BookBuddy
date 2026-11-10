"""
接口级检查（不需要大模型，秒级完成）：知识库增删查清。

    ..\.venv\Scripts\python.exe tests\api_check.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:5000"
ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "test_docs" / "红楼梦-第一至三回.txt"


def stats() -> dict:
    return requests.get(f"{BASE}/api/kb/stats", timeout=120).json()["stats"]


def main() -> int:
    before = stats()
    print(f"起始: {before['source_count']} 文件 / {before['total_chunks']} 片段")

    if not DOC.exists():
        print(f"缺少测试文档: {DOC}")
        return 1

    t0 = time.time()
    with DOC.open("rb") as fh:
        resp = requests.post(
            f"{BASE}/api/kb/upload",
            files={"file": (DOC.name, fh, "text/plain")},
            timeout=900,
        ).json()
    print(f"上传({round(time.time() - t0, 1)}s):", resp.get("results"))

    mid = stats()
    print(f"上传后: {mid['source_count']} 文件 / {mid['total_chunks']} 片段")
    assert DOC.name in mid["sources"], mid["sources"]
    assert mid["total_chunks"] > before["total_chunks"]

    preview = requests.get(f"{BASE}/api/kb/preview", params={"source": DOC.name}, timeout=120).json()
    assert preview["success"] and preview["content"], "预览为空"
    print(f"预览: {len(preview['content'])} 字符")

    # 重新上传同名文件应当是幂等的（先删旧片段）
    with DOC.open("rb") as fh:
        requests.post(f"{BASE}/api/kb/upload", files={"file": (DOC.name, fh, "text/plain")}, timeout=900)
    again = stats()
    assert again["total_chunks"] == mid["total_chunks"], (mid["total_chunks"], again["total_chunks"])
    print(f"重复上传幂等: {again['total_chunks']} 片段（未翻倍）")

    deleted = requests.delete(f"{BASE}/api/kb/delete-source", params={"source": DOC.name}, timeout=300).json()
    print("删除:", deleted.get("message"))
    after = stats()
    print(f"删除后: {after['source_count']} 文件 / {after['total_chunks']} 片段")
    assert after["total_chunks"] == before["total_chunks"], (after["total_chunks"], before["total_chunks"])
    assert DOC.name not in after["sources"]

    print("\n接口检查通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
