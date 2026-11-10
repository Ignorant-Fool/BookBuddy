"""
精排 —— 用 LangChain 的 BaseDocumentCompressor 封装百炼 qwen3-rerank。

把 20 条粗排结果重排并打分，只保留真正相关的片段，避免召回过噪导致幻觉。
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence

import requests
from langchain_core.callbacks import Callbacks
from langchain_core.documents import Document
from langchain_core.documents.compressor import BaseDocumentCompressor
from pydantic import Field

from config import DASHSCOPE_API_KEY, RERANK_URL
from models import registry

logger = logging.getLogger(__name__)


class DashScopeReranker(BaseDocumentCompressor):
    """基于 DashScope text-rerank 的 LangChain 文档压缩器。"""

    model: str = Field(default="")
    api_key: str = Field(default="")
    top_n: int = Field(default=8)
    min_score: float = Field(default=0.0)
    timeout: float = Field(default=20.0)

    def model_post_init(self, __context) -> None:  # noqa: D401
        if not self.model:
            object.__setattr__(self, "model", registry.pick("rerank"))
        if not self.api_key:
            object.__setattr__(self, "api_key", DASHSCOPE_API_KEY)

    # ------------------------------------------------------------------
    def compress_documents(
        self,
        documents: Sequence[Document],
        query: str,
        callbacks: Optional[Callbacks] = None,
    ) -> Sequence[Document]:
        if not documents:
            return []

        payload = {
            "model": self.model,
            "input": {"query": query, "documents": [d.page_content for d in documents]},
            "parameters": {
                "top_n": min(self.top_n, len(documents)),
                "return_documents": False,
            },
        }
        try:
            resp = requests.post(
                RERANK_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            results = (resp.json().get("output") or {}).get("results") or []
        except Exception as exc:
            logger.warning("精排调用失败，退化为原始顺序: %s", exc)
            return list(documents)[: self.top_n]

        ranked: list[Document] = []
        for item in results:
            idx = item.get("index")
            if idx is None or not (0 <= idx < len(documents)):
                continue
            score = float(item.get("relevance_score") or 0.0)
            if score < self.min_score:
                continue
            source_doc = documents[idx]
            meta = dict(source_doc.metadata)
            meta["rerank_score"] = round(score, 4)
            ranked.append(Document(page_content=source_doc.page_content, metadata=meta))

        if not ranked:
            return []
        ranked.sort(key=lambda d: d.metadata.get("rerank_score", 0.0), reverse=True)
        return ranked


def get_reranker(top_n: int = 8, min_score: float = 0.0) -> DashScopeReranker:
    return DashScopeReranker(top_n=top_n, min_score=min_score)
