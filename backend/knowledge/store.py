"""
混合知识库 —— FAISS 向量检索 + BM25 关键词检索，RRF 融合。

持久化目录 data/kb/:
    faiss/index.faiss, faiss/index.pkl   向量索引（LangChain FAISS 格式）
    chunks.json                          全部片段（正文 + metadata）
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Iterable, Sequence

import jieba
import numpy as np
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from config import KB_DIR, RETRIEVE_TOP_K
from knowledge.embeddings import get_embeddings
from knowledge.loaders import load_document
from knowledge.splitter import ChapterAwareTextSplitter

logger = logging.getLogger(__name__)

RRF_K = 60  # RRF 平滑常数

_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_CHAPTER_RE = re.compile(r"第\s*([一二三四五六七八九十百千零两\d]+)\s*[回章节部卷篇集]")


def _chapter_number(text: str) -> int:
    """从片段文本中解析章节序号，用于"首次出场"类问题的排序。"""
    match = _CHAPTER_RE.search(text)
    if not match:
        return 9999
    raw = match.group(1)
    if raw.isdigit():
        return int(raw)
    # 简单中文数字解析（十、十五、二十三…）
    if "十" in raw:
        head, _, tail = raw.partition("十")
        tens = _CN_NUM.get(head, 1) if head else 1
        ones = _CN_NUM.get(tail, 0) if tail else 0
        return tens * 10 + ones
    return _CN_NUM.get(raw[:1], 9999)


def tokenize(text: str) -> list[str]:
    """中文用 jieba 搜索模式分词，英文数字保留。"""
    tokens = []
    for word in jieba.lcut_for_search(text.lower()):
        word = word.strip()
        if not word or word in {"\n", " "}:
            continue
        if re.fullmatch(r"[\W_]+", word):
            continue
        tokens.append(word)
    return tokens


class HybridKnowledgeBase:
    """线程安全的混合检索知识库（进程内单例）。"""

    def __init__(self, kb_dir: Path = KB_DIR) -> None:
        self._dir = Path(kb_dir)
        self._faiss_dir = self._dir / "faiss"
        self._chunks_file = self._dir / "chunks.json"
        self._dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._vs: FAISS | None = None
        self._docs: list[Document] = []
        self._uid_to_pos: dict[str, int] = {}
        self._bm25: BM25Okapi | None = None
        self._bm25_tokens: list[list[str]] = []
        self._loaded = False
        self._splitter = ChapterAwareTextSplitter()

    # ================================================================ 加载 / 持久化
    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_chunks()
            self._load_faiss()
            self._rebuild_bm25()
            self._loaded = True
            logger.info("知识库已加载: %d 个片段 / %d 个文件", len(self._docs), len(self._sources()))

    def _load_chunks(self) -> None:
        if not self._chunks_file.exists():
            self._docs = []
            return
        try:
            raw = json.loads(self._chunks_file.read_text(encoding="utf-8"))
            self._docs = [
                Document(page_content=item["content"], metadata=item.get("metadata") or {})
                for item in raw
            ]
        except Exception as exc:
            logger.error("片段文件损坏，重置知识库: %s", exc)
            self._docs = []
        self._uid_to_pos = {
            str(doc.metadata.get("uid")): i for i, doc in enumerate(self._docs)
        }

    def _load_faiss(self) -> None:
        index_file = self._faiss_dir / "index.faiss"
        if not index_file.exists():
            self._vs = None
            return
        try:
            self._vs = FAISS.load_local(
                str(self._faiss_dir),
                get_embeddings(),
                allow_dangerous_deserialization=True,
            )
        except Exception as exc:
            logger.error("FAISS 索引加载失败，将按需重建: %s", exc)
            self._vs = None

    def _save(self) -> None:
        try:
            self._chunks_file.write_text(
                json.dumps(
                    [
                        {"content": d.page_content, "metadata": d.metadata}
                        for d in self._docs
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("片段持久化失败: %s", exc)

        try:
            if self._vs is not None and self._docs:
                self._faiss_dir.mkdir(parents=True, exist_ok=True)
                self._vs.save_local(str(self._faiss_dir))
            elif self._faiss_dir.exists():
                for f in self._faiss_dir.glob("*"):
                    f.unlink(missing_ok=True)
        except Exception as exc:
            logger.error("FAISS 持久化失败: %s", exc)

    def _rebuild_bm25(self) -> None:
        if not self._docs:
            self._bm25 = None
            self._bm25_tokens = []
            return
        self._bm25_tokens = [tokenize(d.page_content) for d in self._docs]
        try:
            self._bm25 = BM25Okapi(self._bm25_tokens)
        except Exception as exc:
            logger.warning("BM25 构建失败: %s", exc)
            self._bm25 = None

    # ================================================================ 写入
    def add_file(self, path: str | Path, source_name: str | None = None) -> dict[str, Any]:
        """加载 → 切片 → 向量化 → 入库。返回处理统计。"""
        self._ensure_loaded()
        doc = load_document(path, source_name=source_name)
        chunks = self._splitter.split_documents([doc])
        if not chunks:
            return {"file": doc.metadata.get("source"), "chunks": 0, "chars": len(doc.page_content)}

        added = self.add_documents(chunks, source=doc.metadata["source"])
        return {
            "file": doc.metadata["source"],
            "chars": len(doc.page_content),
            "chunks": added,
        }

    def add_documents(self, documents: Sequence[Document], source: str) -> int:
        """批量写入片段；同名文件会先删除旧片段（幂等重传）。"""
        if not documents:
            return 0
        self._ensure_loaded()
        with self._lock:
            if source in self._sources():
                self._delete_locked(source)

            book = Path(source).stem
            prepared: list[Document] = []
            for index, doc in enumerate(documents):
                meta = dict(doc.metadata)
                meta["source"] = source
                meta["book"] = book
                meta["chunk_index"] = int(meta.get("chunk_index", index))
                meta["uid"] = f"{source}#{meta['chunk_index']}"
                content = doc.page_content
                if not content.startswith("【书籍"):
                    content = f"【书籍：《{book}》】\n{content}"
                prepared.append(Document(page_content=content, metadata=meta))

            # 向量化入库
            if self._vs is None:
                self._vs = FAISS.from_documents(
                    prepared,
                    get_embeddings(),
                    ids=[d.metadata["uid"] for d in prepared],
                )
            else:
                self._vs.add_documents(
                    prepared, ids=[d.metadata["uid"] for d in prepared]
                )

            for doc in prepared:
                self._uid_to_pos[doc.metadata["uid"]] = len(self._docs)
                self._docs.append(doc)

            self._rebuild_bm25()
            self._save()
            logger.info("写入知识库: %s -> %d 个片段", source, len(prepared))
            return len(prepared)

    # ================================================================ 检索
    def search(self, query: str, top_k: int = RETRIEVE_TOP_K) -> list[Document]:
        """向量 + BM25 混合检索，RRF 融合。返回的 Document.metadata 带 score / distance。"""
        self._ensure_loaded()
        with self._lock:
            docs = list(self._docs)
        if not docs:
            return []

        fused: dict[str, float] = {}
        distances: dict[str, float] = {}

        # 1) 向量检索
        vector_hits: list[tuple[Document, float]] = []
        if self._vs is not None:
            try:
                vector_hits = self._vs.similarity_search_with_score(query, k=min(top_k, len(docs)))
            except Exception as exc:
                logger.warning("向量检索失败，降级为 BM25: %s", exc)
                vector_hits = []

        for rank, (doc, distance) in enumerate(vector_hits):
            uid = str(doc.metadata.get("uid") or doc.page_content[:80])
            fused[uid] = fused.get(uid, 0.0) + 1.0 / (RRF_K + rank + 1)
            distances[uid] = float(distance)

        # 2) BM25 关键词检索（始终参与）
        if self._bm25 is not None and self._docs:
            try:
                scores = self._bm25.get_scores(tokenize(query))
                order = np.argsort(scores)[::-1][:top_k]
                for rank, pos in enumerate(order):
                    if pos >= len(self._docs) or scores[pos] <= 0:
                        continue
                    uid = str(self._docs[pos].metadata.get("uid"))
                    fused[uid] = fused.get(uid, 0.0) + 1.0 / (RRF_K + rank + 1)
            except Exception as exc:
                logger.warning("BM25 检索失败: %s", exc)

        if not fused:
            return []

        ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        by_uid = {str(d.metadata.get("uid")): d for d in self._docs}
        results: list[Document] = []
        for uid, score in ordered:
            doc = by_uid.get(uid)
            if doc is None:
                continue
            meta = dict(doc.metadata)
            meta["score"] = round(score, 6)
            meta["distance"] = round(distances.get(uid, 1.0), 4)
            results.append(Document(page_content=doc.page_content, metadata=meta))
        return results

    def scan(self, entity: str, limit: int = 30) -> list[Document]:
        """绕过向量检索：硬过滤实体 + 按章节号升序 —— 专治"第一次出场在第几回"。"""
        self._ensure_loaded()
        if not entity:
            return []
        with self._lock:
            docs = list(self._docs)

        matches = [d for d in docs if entity in d.page_content]
        seen: set[str] = set()
        unique: list[Document] = []
        for doc in matches:
            key = doc.page_content[:80]
            if key in seen:
                continue
            seen.add(key)
            unique.append(doc)

        try:
            unique.sort(key=lambda d: _chapter_number(d.page_content))
        except Exception:
            pass  # 排序失败不阻塞

        out: list[Document] = []
        for doc in unique[:limit]:
            meta = dict(doc.metadata)
            meta.setdefault("score", 0.02)
            meta["scan"] = True
            out.append(Document(page_content=doc.page_content, metadata=meta))
        return out

    # ================================================================ 查询 / 维护
    def _sources(self) -> list[str]:
        seen: list[str] = []
        for doc in self._docs:
            source = str(doc.metadata.get("source") or "")
            if source and source not in seen:
                seen.append(source)
        return seen

    def stats(self) -> dict[str, Any]:
        self._ensure_loaded()
        with self._lock:
            sources = self._sources()
            return {
                "total_chunks": len(self._docs),
                "sources": sources,
                "source_count": len(sources),
            }

    def preview(self, source: str) -> str:
        self._ensure_loaded()
        with self._lock:
            chunks = [
                (int(d.metadata.get("chunk_index", 0)), d.page_content)
                for d in self._docs
                if d.metadata.get("source") == source
            ]
        chunks.sort(key=lambda item: item[0])
        return "\n\n".join(text for _, text in chunks)

    def all_chunks(self, limit: int = 2000) -> list[str]:
        self._ensure_loaded()
        with self._lock:
            return [d.page_content for d in self._docs[:limit]]

    def sample_chunks(self, limit: int = 200) -> list[str]:
        """跨全书均匀采样，避免只看开头几章（人物抽取用）。"""
        self._ensure_loaded()
        with self._lock:
            docs = list(self._docs)
        if not docs:
            return []
        if len(docs) <= limit:
            return [d.page_content for d in docs]
        step = len(docs) / limit
        return [docs[min(int(i * step), len(docs) - 1)].page_content for i in range(limit)]

    def is_empty(self) -> bool:
        self._ensure_loaded()
        return len(self._docs) == 0

    def delete_source(self, source: str) -> bool:
        self._ensure_loaded()
        with self._lock:
            return self._delete_locked(source)

    def _delete_locked(self, source: str) -> bool:
        before = len(self._docs)
        remove = [d for d in self._docs if d.metadata.get("source") == source]
        if not remove:
            return False

        ids = [str(d.metadata.get("uid")) for d in remove]
        if self._vs is not None:
            try:
                self._vs.delete(ids)
            except Exception as exc:
                logger.warning("FAISS 删除失败，将重建索引: %s", exc)
                self._rebuild_faiss_locked(exclude_source=source)

        self._docs = [d for d in self._docs if d.metadata.get("source") != source]
        self._uid_to_pos = {str(d.metadata.get("uid")): i for i, d in enumerate(self._docs)}
        self._rebuild_bm25()
        self._save()
        logger.info("删除文件 %s: %d -> %d 个片段", source, before, len(self._docs))
        return True

    def _rebuild_faiss_locked(self, exclude_source: str | None = None) -> None:
        remaining = [d for d in self._docs if d.metadata.get("source") != exclude_source]
        if not remaining:
            self._vs = None
            return
        self._vs = FAISS.from_documents(
            remaining,
            get_embeddings(),
            ids=[str(d.metadata.get("uid")) for d in remaining],
        )

    def clear(self) -> None:
        self._ensure_loaded()
        with self._lock:
            self._docs = []
            self._uid_to_pos = {}
            self._vs = None
            self._bm25 = None
            self._bm25_tokens = []
            for path in (self._chunks_file,):
                path.unlink(missing_ok=True)
            if self._faiss_dir.exists():
                for f in self._faiss_dir.glob("*"):
                    f.unlink(missing_ok=True)
            logger.info("知识库已清空")


# 进程内单例
knowledge_base = HybridKnowledgeBase()
