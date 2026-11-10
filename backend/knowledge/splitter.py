"""
语义切片器 —— 继承 LangChain TextSplitter，按"章节 + 段落"边界切分。

相对通用 RecursiveCharacterTextSplitter 的改进：
* 先识别章节标题（第X回/第X章/Chapter X/上卷…），保证一章不被切断；
* 每个切片前缀上【章节：xxx】元数据，显著提升"第X回讲了什么"这类查询的召回；
* 超长段落按句末标点软切，保持句子完整；
* 片段的 chapter 写入 metadata，供检索结果引用。
"""
from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

from langchain_core.documents import Document
from langchain_text_splitters import TextSplitter

from config import CHUNK_SIZE, MIN_CHUNK_CHARS

# 章节标题模式：中文章回体 / 现代章节 / 英文 / 卷篇
CHAPTER_PATTERNS = [
    re.compile(r"^第[一二三四五六七八九十百千零两\d]+[回章节部卷篇集]"),
    re.compile(r"^Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"^第?[一二三四五六七八九十百千\d]+[、，．.\s]"),
    re.compile(r"^[（(][一二三四五六七八九十\d]+[）)]"),
    re.compile(r"^[上中下][卷篇部集]"),
    re.compile(r"^【第\s*\d+\s*页】"),
]

DEFAULT_CHAPTER = "正文"


class ChapterAwareTextSplitter(TextSplitter):
    """按章节 / 段落边界切分的 LangChain TextSplitter 实现。"""

    # TextSplitter 是 pydantic 模型，自定义属性必须声明成字段
    min_chunk_chars: int = MIN_CHUNK_CHARS

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = 0,
        min_chunk_chars: int = MIN_CHUNK_CHARS,
        **kwargs,
    ) -> None:
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap, **kwargs)
        self.min_chunk_chars = int(min_chunk_chars)

    @property
    def max_chars(self) -> int:
        """当前生效的片段长度上限（兼容不同版本的 TextSplitter 属性名）。"""
        return int(getattr(self, "_chunk_size", CHUNK_SIZE))

    # ---------------------------------------------------------- 公共接口
    def split_text(self, text: str) -> List[str]:
        return [chunk for _, chunk in self.split_text_with_meta(text)]

    def split_text_with_meta(self, text: str) -> List[Tuple[str, str]]:
        """返回 [(章节名, 片段文本), ...]，片段文本已带章节前缀。"""
        indexed = self._split_by_chapter(text)
        # 去重（前 60 字符相同视为重复）
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        for chapter, chunk in indexed:
            key = chunk[:60]
            if key in seen:
                continue
            seen.add(key)
            result.append((chapter, chunk))
        return result

    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        """切分并把 chapter 写入 metadata。"""
        output: list[Document] = []
        for doc in documents:
            for order, (chapter, chunk) in enumerate(self.split_text_with_meta(doc.page_content)):
                meta = dict(doc.metadata)
                meta["chapter"] = chapter
                meta["chunk_index"] = order
                output.append(Document(page_content=chunk, metadata=meta))
        return output

    # ---------------------------------------------------------- 内部实现
    def _split_by_chapter(self, text: str) -> List[Tuple[str, str]]:
        lines = text.split("\n")
        chapters: list[tuple[str, int, int]] = []
        current_title = DEFAULT_CHAPTER
        chapter_start = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if len(stripped) <= 40 and any(p.match(stripped) for p in CHAPTER_PATTERNS):
                if i > chapter_start:
                    chapters.append((current_title, chapter_start, i))
                current_title = stripped
                chapter_start = i

        if chapter_start < len(lines):
            chapters.append((current_title, chapter_start, len(lines)))

        # 没识别到任何章节 -> 整篇作为一章
        if len(chapters) <= 1 and (not chapters or chapters[0][0] == DEFAULT_CHAPTER):
            chapters = [(DEFAULT_CHAPTER, 0, len(lines))]

        chunks: list[tuple[str, str]] = []
        for title, start, end in chapters:
            chapter_text = "\n".join(lines[start:end]).strip()
            if not chapter_text:
                continue
            chunks.extend(self._split_chapter(title, chapter_text))

        # 兜底：短文档 / 全是短段落时可能一条都没产出，直接整篇作为单片段
        if not chunks and text.strip():
            chunks = [(DEFAULT_CHAPTER, text.strip())]
        return chunks

    def _split_chapter(self, title: str, chapter_text: str) -> List[Tuple[str, str]]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", chapter_text) if p.strip()]
        result: list[tuple[str, str]] = []
        buffer = ""

        for para in paragraphs:
            # 跳过章节标题行本身（已存为 title）
            if len(para) <= 50 and any(p.match(para) for p in CHAPTER_PATTERNS):
                continue

            if len(buffer) + len(para) <= self.max_chars:
                buffer += para + "\n\n"
                continue

            # 章节里第一条即使偏短也保留，避免短段落被整体丢弃
            if buffer.strip() and (len(buffer.strip()) >= self.min_chunk_chars or not result):
                result.append((title, self._decorate(buffer.strip(), title)))

            if len(para) > self.max_chars:
                for sub in self._soft_split(para, self.max_chars):
                    if len(sub) >= self.min_chunk_chars or not result:
                        result.append((title, self._decorate(sub, title)))
                buffer = ""
            else:
                buffer = para + "\n\n"

        if buffer.strip() and (len(buffer.strip()) >= self.min_chunk_chars or not result):
            result.append((title, self._decorate(buffer.strip(), title)))
        return result

    @staticmethod
    def _decorate(text: str, chapter: str) -> str:
        """给片段加上章节前缀，提升 embedding 对章节类问题的敏感度。"""
        if chapter and chapter != DEFAULT_CHAPTER:
            return f"【章节：{chapter}】\n{text}"
        return text

    @staticmethod
    def _soft_split(text: str, max_size: int) -> List[str]:
        sentences = re.split(r"(?<=[。！？!?；;\n])", text)
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) <= max_size:
                current += sentence
                continue
            if current.strip():
                chunks.append(current.strip())
            if len(sentence) > max_size:
                for i in range(0, len(sentence), max_size):
                    piece = sentence[i : i + max_size].strip()
                    if piece:
                        chunks.append(piece)
                current = ""
            else:
                current = sentence
        if current.strip():
            chunks.append(current.strip())
        return chunks


def split_documents(documents: Sequence[Document]) -> List[Document]:
    """便捷函数：用默认参数切分文档。"""
    return ChapterAwareTextSplitter().split_documents(documents)
