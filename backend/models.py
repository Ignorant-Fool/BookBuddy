"""
模型自动选择 —— 启动时探测当前 API KEY 可见的模型，为每个角色挑一个最合适的。

策略：
1. 请求 OpenAI 兼容接口 /models 拿到全部可用模型（带磁盘缓存，离线时用缓存）。
2. 按 config.MODEL_CANDIDATES 的优先级，取第一个"真实存在"的候选。
3. 若某个角色一个候选都没有命中，则退化为该角色候选列表的第一个（乐观尝试）。
4. .env 中显式指定的模型永远优先（方便用户锁定）。
5. 支持运行期按问题复杂度动态选择生成模型（fast / chat / agent）。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

import requests

from config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    MODEL_CACHE_FILE,
    MODEL_CANDIDATES,
    ROLE_ENV_OVERRIDE,
)

logger = logging.getLogger(__name__)

_ROLES = ("agent", "chat", "fast", "embedding", "rerank", "asr")
_CACHE_TTL = 60 * 60 * 12  # 12 小时

# 这些角色的 /models 列表不可靠（ASR 用别名、部分条目在本网关下不可调用），
# 直接按候选顺序取第一个，再由运行期真实调用结果纠正。
PROBE_FIRST_ROLES = {"asr"}


class ModelRegistry:
    """负责发现 / 选择模型，并在整个进程内缓存结果。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._available: list[str] = []
        self._available_set: set[str] = set()
        self._fetched_at: float = 0.0
        self._resolved: dict[str, str] = {}
        self._sources: dict[str, str] = {}
        self._load_cache()

    # ------------------------------------------------------------ 发现
    def _load_cache(self) -> None:
        try:
            if MODEL_CACHE_FILE.exists():
                raw = json.loads(MODEL_CACHE_FILE.read_text(encoding="utf-8"))
                models = raw.get("models") or []
                if isinstance(models, list) and models:
                    self._available = [str(m) for m in models]
                    self._available_set = set(self._available)
                    self._fetched_at = float(raw.get("fetched_at") or 0)
        except Exception as exc:  # 缓存损坏不影响启动
            logger.warning("模型缓存读取失败: %s", exc)

    def _save_cache(self) -> None:
        try:
            MODEL_CACHE_FILE.write_text(
                json.dumps(
                    {"models": self._available, "fetched_at": self._fetched_at},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("模型缓存写入失败: %s", exc)

    def refresh(self, force: bool = False, timeout: float = 20.0) -> list[str]:
        """拉取 /models。失败时退回磁盘缓存。"""
        with self._lock:
            fresh_enough = (time.time() - self._fetched_at) < _CACHE_TTL and self._available
            if fresh_enough and not force:
                return list(self._available)

        models: list[str] = []
        try:
            resp = requests.get(
                f"{DASHSCOPE_BASE_URL}/models",
                headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
                timeout=timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
            models = sorted(
                str(item["id"]) for item in payload.get("data", []) if item.get("id")
            )
            logger.info("已发现 %d 个可用模型", len(models))
        except Exception as exc:
            logger.warning("拉取模型列表失败（将使用缓存/候选列表）: %s", exc)
            with self._lock:
                return list(self._available)

        with self._lock:
            self._available = models
            self._available_set = set(models)
            self._fetched_at = time.time()
            self._resolved.clear()  # 重新选择
            self._sources.clear()
            self._save_cache()
        return list(models)

    # ------------------------------------------------------------ 选择
    @property
    def available(self) -> list[str]:
        with self._lock:
            return list(self._available)

    def exists(self, model: str) -> bool:
        with self._lock:
            # 模型列表可能不含别名（如 qwen3-asr-flash），无法确认时按"可能存在"处理
            return (not self._available) or (model in self._available_set)

    def pick(self, role: str) -> str:
        """选出某个角色的模型（带缓存）。"""
        with self._lock:
            if role in self._resolved:
                return self._resolved[role]

        override = os.getenv(ROLE_ENV_OVERRIDE.get(role, ""), "").strip()
        if override:
            chosen, source = override, "env"
        else:
            candidates = MODEL_CANDIDATES.get(role) or []
            if not candidates:
                raise ValueError(f"未知模型角色: {role}")
            chosen = ""
            source = ""
            if role in PROBE_FIRST_ROLES:
                chosen, source = candidates[0], "probe-first"
            else:
                with self._lock:
                    for cand in candidates:
                        if cand in self._available_set:
                            chosen, source = cand, "auto"
                            break
            if not chosen:
                # 一个都没命中：乐观使用首选候选（例如 ASR 别名不在 /models 中）
                chosen, source = candidates[0], "auto-fallback"

        with self._lock:
            self._resolved[role] = chosen
            self._sources[role] = source
        logger.info("模型选择 [%s] -> %s (%s)", role, chosen, source)
        return chosen

    def resolve_all(self) -> dict[str, str]:
        return {role: self.pick(role) for role in _ROLES}

    def override(self, role: str, model: str) -> None:
        """运行期发现更合适的模型（例如 ASR 逐个试出来的可用模型）时更新记录。"""
        if not model:
            return
        with self._lock:
            if self._resolved.get(role) == model:
                return
            self._resolved[role] = model
            self._sources[role] = "runtime-probe"
        logger.info("模型选择 [%s] 运行期更新为 %s", role, model)

    def generation_model(self, qtype: str, evidence_count: int) -> str:
        """按问题复杂度动态选择生成模型 —— 简单快答，复杂深思。"""
        complex_types = ("对比分析", "复杂推理", "列举梳理", "时间线")
        simple_types = ("事实查询", "定义解释")

        if qtype in complex_types or evidence_count >= 8:
            return self.pick("agent")
        if qtype in simple_types and evidence_count <= 4:
            return self.pick("fast")
        return self.pick("chat")

    def describe(self) -> dict[str, Any]:
        with self._lock:
            resolved = {role: self._resolved.get(role) or self.pick(role) for role in _ROLES}
            sources = dict(self._sources)
            available = list(self._available)
            fetched_at = self._fetched_at
        return {
            "resolved": resolved,
            "sources": sources,
            "available_count": len(available),
            "available": available,
            "fetched_at": fetched_at,
        }


registry = ModelRegistry()


def warm_up() -> None:
    """进程启动时调用：拉模型列表 + 解析所有角色。"""
    registry.refresh()
    resolved = registry.resolve_all()
    logger.info("模型角色解析完成: %s", json.dumps(resolved, ensure_ascii=False))
