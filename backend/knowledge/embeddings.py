"""
向量化 —— 通过 LangChain 的 OpenAIEmbeddings 调用百炼 text-embedding。
"""
from __future__ import annotations

import logging
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL
from models import registry

logger = logging.getLogger(__name__)

# 百炼 embedding 单次请求最多 25 条（不同模型略有差异，取保守值）
EMBED_BATCH_SIZE = 10


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    model = registry.pick("embedding")
    logger.info("Embedding 模型: %s", model)
    return OpenAIEmbeddings(
        model=model,
        api_key=DASHSCOPE_API_KEY,
        base_url=DASHSCOPE_BASE_URL,
        chunk_size=EMBED_BATCH_SIZE,
        # 关掉 tiktoken 预切分：直接按字符串批量发给百炼，避免 tokenizer 不匹配
        check_embedding_ctx_length=False,
        max_retries=3,
        timeout=60,
    )


def embedding_dimension() -> int:
    """探测当前 embedding 模型维度。"""
    vector = get_embeddings().embed_query("维度探测")
    return len(vector)
