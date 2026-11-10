"""多轮对话检查：验证会话记忆是否生效。"""
import sys

import requests

BASE = "http://127.0.0.1:5000"
SESSION = "multiturn_demo"

QUESTIONS = [
    "林黛玉的父亲是谁？",
    "她母亲叫什么名字？",  # 代词指代，需要上一轮上下文
]


def ask(question: str) -> dict:
    return requests.post(
        f"{BASE}/api/send-text",
        json={"text": question, "session_id": SESSION},
        timeout=600,
    ).json()


def main() -> int:
    for index, question in enumerate(QUESTIONS, 1):
        data = ask(question)
        print(f"\n--- 第 {index} 轮: {question}")
        print(f"    模型: {data.get('model')}  耗时: {data.get('elapsed')}s  证据: {data.get('evidence_count')}")
        print("    回答:", (data.get("llm_answer") or "").replace("\n", " ")[:300])
        for step in data.get("agent_steps", []):
            print(f"      · [{step['type']}] {step['content'][:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
