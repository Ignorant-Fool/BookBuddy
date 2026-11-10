"""
人物关系抽取 —— 从知识库内容里让大模型结构化输出人物与关系。

实现要点：
* 用 LangChain 的消息 + 模型调用（prompt → model → 结构化解析）。
* 上下文采用「跨全书均匀采样」，避免只看开头几章。
* 模型输出可能因为 max_tokens 被截断（finish_reason=length），
  因此除了标准 JSON 解析外，还实现了「按对象逐个抢救」的容错解析。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import prompts
from knowledge.store import knowledge_base
from llm import invoke_text, to_messages

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 30000
MAX_OUTPUT_TOKENS = 4000


def _clean_raw(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return raw


def _extract_objects(raw: str) -> list[dict[str, Any]]:
    """从可能被截断的 JSON 中，逐个抢救出完整的人物对象。"""
    anchor = raw.find('"characters"')
    start = raw.find("[", anchor if anchor >= 0 else 0)
    if start < 0:
        return []

    objects: list[dict[str, Any]] = []
    i, n = start + 1, len(raw)
    while i < n:
        while i < n and raw[i] in " \t\r\n,":
            i += 1
        if i >= n or raw[i] != "{":
            break

        depth, in_string, escaped = 0, False, False
        j = i
        while j < n:
            ch = raw[j]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1

        if j >= n:  # 最后一个对象不完整，丢弃
            break
        try:
            obj = json.loads(raw[i : j + 1])
            if isinstance(obj, dict) and obj.get("name"):
                objects.append(obj)
        except Exception:
            pass
        i = j + 1
    return objects


def _parse(raw: str) -> list[dict[str, Any]]:
    cleaned = _clean_raw(raw)
    for candidate in (cleaned, cleaned[cleaned.find("{") :] if "{" in cleaned else ""):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        characters = data.get("characters") if isinstance(data, dict) else None
        if isinstance(characters, list):
            return [c for c in characters if isinstance(c, dict)]
    # 截断 / 语法错误 -> 逐个对象抢救
    salvaged = _extract_objects(cleaned)
    if salvaged:
        logger.warning("人物 JSON 被截断，已抢救出 %d 个人物", len(salvaged))
    return salvaged


def _normalize(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        entry: dict[str, Any] = {"name": name}
        if item.get("relation"):
            entry["relation"] = str(item["relation"]).strip()
        if item.get("description"):
            entry["description"] = str(item["description"]).strip()
        relations = item.get("relations")
        if isinstance(relations, list):
            entry["relations"] = [
                {
                    "with": str(r.get("with") or "").strip(),
                    "type": str(r.get("type") or "").strip(),
                }
                for r in relations
                if isinstance(r, dict) and r.get("with")
            ][:6]
        cleaned.append(entry)
    return cleaned


def extract_characters(query: str = "") -> dict[str, Any]:
    chunks = knowledge_base.sample_chunks(limit=200)
    if not chunks:
        raise ValueError("知识库为空，请先上传书籍文件")

    combined = "\n\n".join(chunks)[:MAX_CONTEXT_CHARS]
    if query:
        prompt = prompts.CHARACTER_PROMPT_WITH_QUERY.format(query=query, text=combined)
    else:
        prompt = prompts.CHARACTER_PROMPT_ALL.format(text=combined)

    raw = invoke_text(
        to_messages(
            "你是中国古典文学与小说文本的分析专家，只输出合法 JSON，不要任何解释。",
            None,
            prompt,
        ),
        role="agent",
        temperature=0.1,
        max_tokens=MAX_OUTPUT_TOKENS,
    )

    items = _parse(raw)
    if not items:
        logger.warning("人物抽取无法解析，原始输出前 300 字: %s", (raw or "")[:300])
        return {"characters": []}
    return {"characters": _normalize(items)}
