"""
文本清洗 —— 把 ASR 输出规范化为可直接检索的问题。

以 LangChain Runnable 的形式提供，可无缝并入 LCEL 链。
"""
from __future__ import annotations

import re

from langchain_core.runnables import RunnableLambda


def clean_text(text: str) -> str:
    """标点规范化 + 去冗余空白 + 去掉无意义的句首标点。"""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    text = re.sub(r"^\s*[，,。.、；;：:]\s*", "", text)
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"[。.]{2,}", "。", text)
    text = re.sub(r"[？?]{2,}", "？", text)
    # 去除 ASR 偶发的语气词开头
    text = re.sub(r"^(嗯+|呃+|啊+|哦+)[，,、\s]*", "", text)
    return text.strip()


clean_chain = RunnableLambda(clean_text).with_config(run_name="clean_asr_text")
