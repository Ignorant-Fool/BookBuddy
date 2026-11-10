"""
会话记忆 —— 轻量 JSON 持久化，供多轮对话使用。

（Agent 内部只用最近若干轮，历史保存在这里以便重启后继续追问）
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from config import MAX_HISTORY_TURNS, MAX_SESSIONS, SESSIONS_FILE

logger = logging.getLogger(__name__)


class SessionStore:
    def __init__(self, path: Path = SESSIONS_FILE, max_sessions: int = MAX_SESSIONS) -> None:
        self._path = Path(path)
        self._max = max_sessions
        self._lock = threading.RLock()
        self._sessions: dict[str, list[dict[str, Any]]] = self._load()

    # ------------------------------------------------------------------
    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): list(v) for k, v in data.items() if isinstance(v, list)}
        except Exception as exc:
            logger.warning("会话文件损坏，使用空会话: %s", exc)
        return {}

    def _save_locked(self) -> None:
        try:
            if len(self._sessions) > self._max:
                for key in sorted(self._sessions.keys())[: len(self._sessions) - self._max]:
                    del self._sessions[key]
            self._path.write_text(
                json.dumps(self._sessions, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.error("会话保存失败: %s", exc)

    # ------------------------------------------------------------------
    def history(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._sessions.get(session_id, []))

    def append_turn(self, session_id: str, question: str, answer: str) -> None:
        with self._lock:
            messages = self._sessions.setdefault(session_id, [])
            messages.append({"role": "user", "content": question})
            messages.append({"role": "assistant", "content": answer})
            # 只保留最近 N 轮
            limit = MAX_HISTORY_TURNS * 2
            if len(messages) > limit:
                del messages[: len(messages) - limit]
            self._save_locked()

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            self._save_locked()

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def summary(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"session_id": sid, "turns": len(msgs) // 2}
                for sid, msgs in self._sessions.items()
            ]


session_store = SessionStore()
