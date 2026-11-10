"""
LangChain 模型工厂 + 统一调用封装。

所有 LLM 调用都走 langchain_openai.ChatOpenAI，指向阿里云百炼的 OpenAI 兼容端点。

稳定性设计（这几点是实测踩坑后加的）：
* 默认关闭"思考模式"（enable_thinking=False）。百炼上的 qwen3.x 默认会先输出大段
  reasoning_content，如果 max_tokens 被思考过程吃满，content 会变成空字符串。
  关掉后同样的 prompt 通常 1 秒内返回，且不会空。
* 空内容自动换模型重试：主模型返回空时，按同角色候选顺序再试，仍失败再退到 chat 模型。
* temperature / thinking 参数不被接受时自动降级重试。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, ENABLE_THINKING, MODEL_CANDIDATES
from models import registry

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")
_MAX_FALLBACKS = 3


def _thinking_body(enabled: bool | None = None) -> dict[str, Any] | None:
    if enabled is None:
        enabled = ENABLE_THINKING
    return None if enabled else {"enable_thinking": False}


def _build(name: str, temperature: float | None, max_tokens: int, thinking: bool | None) -> ChatOpenAI:
    kwargs: dict[str, Any] = {
        "model": name,
        "api_key": DASHSCOPE_API_KEY,
        "base_url": DASHSCOPE_BASE_URL,
        "max_tokens": max_tokens,
        "timeout": 120,
        "max_retries": 2,
        "extra_body": _thinking_body(thinking),
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    return ChatOpenAI(**kwargs)


def get_chat_model(
    role: str = "chat",
    *,
    temperature: float = 0.1,
    max_tokens: int = 1500,
    model: str | None = None,
    thinking: bool | None = None,
) -> ChatOpenAI:
    """按角色（agent / chat / fast）或显式模型名构造 ChatOpenAI。"""
    return _build(model or registry.pick(role), temperature, max_tokens, thinking)


def to_messages(system: str | None, history: Sequence[dict] | None, prompt: str) -> list[BaseMessage]:
    """把 OpenAI 风格的 history 转成 LangChain 消息列表。"""
    msgs: list[BaseMessage] = []
    if system:
        msgs.append(SystemMessage(content=system))
    for item in history or []:
        role = item.get("role")
        content = item.get("content") or ""
        if not content:
            continue
        if role == "user":
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
    msgs.append(HumanMessage(content=prompt))
    return msgs


def _fallback_chain(role: str, primary: str) -> list[str]:
    """主模型 → 同角色其它候选 → chat 角色模型。"""
    chain = [primary]
    for name in MODEL_CANDIDATES.get(role, []):
        if name not in chain:
            chain.append(name)
        if len(chain) >= _MAX_FALLBACKS:
            break
    if len(chain) < _MAX_FALLBACKS:
        try:
            chat_model = registry.pick("chat")
            if chat_model not in chain:
                chain.append(chat_model)
        except Exception:
            pass
    return chain[:_MAX_FALLBACKS]


def invoke_text(
    messages: Iterable[BaseMessage],
    *,
    role: str = "chat",
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 1500,
    thinking: bool | None = None,
) -> str:
    """调用模型返回纯文本；空内容 / 参数不兼容时自动换模型重试。"""
    payload = list(messages)
    primary = model or registry.pick(role)
    last_error: Exception | None = None

    for attempt, name in enumerate(_fallback_chain(role, primary)):
        budget = max_tokens if attempt == 0 else max(max_tokens, 2500)
        try:
            resp = _build(name, temperature, budget, thinking).invoke(payload)
            text = (resp.content or "").strip()
            if text:
                if attempt:
                    logger.info("备用模型 %s 成功（主模型 %s 不可用）", name, primary)
                return text
            logger.warning("模型 %s 返回空内容（可能思考过程吃满了 token），尝试下一个", name)
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            if "temperature" in message:
                try:
                    resp = _build(name, None, budget, thinking).invoke(payload)
                    text = (resp.content or "").strip()
                    if text:
                        return text
                except Exception as retry_exc:
                    last_error = retry_exc
            logger.warning("模型 %s 调用失败: %s", name, exc)

    if last_error:
        raise last_error
    return ""


def invoke_json(
    prompt: str,
    *,
    role: str = "agent",
    system: str | None = None,
    temperature: float = 0.05,
    max_tokens: int = 800,
    default: dict | None = None,
) -> dict[str, Any]:
    """要求模型输出 JSON，尽最大努力解析；失败返回 default。"""
    messages = to_messages(system, None, prompt)
    try:
        raw = invoke_text(messages, role=role, temperature=temperature, max_tokens=max_tokens)
    except Exception as exc:
        logger.warning("JSON 调用失败: %s", exc)
        return default or {}

    if not raw:
        return default or {}

    candidates = [raw, re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()]
    match = _JSON_BLOCK.search(raw)
    if match:
        candidates.append(match.group())

    for text in candidates:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    logger.warning("JSON 解析失败，原始输出: %s", raw[:300])
    return default or {}
