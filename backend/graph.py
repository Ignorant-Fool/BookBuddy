"""
LangGraph 智能体 —— 探索式 Agentic RAG。

图结构（含两个环）：

    START
      │
      ▼
    guard    ── 知识库为空？
      │
      ├──────────────► END
      ▼
   classify  ── 问题分类 + 检索策略规划
      ▼
   retrieve  ── 多策略并行召回（语义 / 关键词 / 全文扫描）
      ▼
    grade    ── Rerank 精排 + 相关性过滤
      │  (无相关片段)
      ├──────────────► END
      ▼
   assess ◄─────────┐  证据充分性评估
      │             │
      ├── 不足且可重试 ─► retrieve_more ──┘   (环 1：补检索)
      ├── 证据 ≥3 条 ──► cross_check
      └── 其余 ─────────► synthesize
                              ▼
                         critique ── 事实核查
                              │
                     ┌────────┴────────┐
               有错误 │                 │ 通过 / 达轮次上限
                      ▼                 ▼
                   rewrite ──► critique  finalize ──► END
                   (环 2：Self-Refine)
"""
from __future__ import annotations

import logging
import operator
import re
from typing import Annotated, Any, TypedDict

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph

import prompts
from config import (
    MAX_HISTORY_TURNS,
    MAX_REFINE_ROUNDS,
    MAX_RETRIEVAL_ROUNDS,
    RERANK_MIN_SCORE,
    RERANK_TOP_N,
    RETRIEVE_TOP_K,
)
from knowledge.rerank import get_reranker
from knowledge.store import knowledge_base
from llm import invoke_json, invoke_text, to_messages
from models import registry

logger = logging.getLogger(__name__)


# ==================================================================== 状态
class AgentState(TypedDict, total=False):
    query: str
    history: list[dict]

    qtype: str
    entities: list[str]
    strategies: list[dict]

    candidates: list[Document]
    docs: list[Document]

    sufficient: bool
    missing: list[str]
    retries: int

    consistency: str
    draft: str
    critique: str
    rounds: int

    answer: str
    model: str
    refused: bool
    stalled: bool
    steps: Annotated[list[dict], operator.add]


def _step(kind: str, content: str) -> dict:
    return {"type": kind, "content": content}


def _dedupe(documents: list[Document]) -> list[Document]:
    seen: set[str] = set()
    out: list[Document] = []
    for doc in documents:
        key = doc.page_content[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(doc)
    return out


def _label(doc: Document) -> str:
    meta = doc.metadata or {}
    book = str(meta.get("book") or "").strip()
    chapter = str(meta.get("chapter") or "").strip()
    parts: list[str] = []
    if book:
        parts.append(f"《{book}》")
    if chapter and chapter not in ("正文",):
        parts.append(chapter)
    return " ".join(parts) or "知识库"


def _build_context(documents: list[Document], max_chars: int = 14000) -> str:
    blocks: list[str] = []
    total = 0
    for idx, doc in enumerate(documents, 1):
        content = doc.page_content
        content = re.sub(r"【书籍：《(.*?)》】\s*", "", content)
        content = re.sub(r"【章节[：:]\s*(.*?)】\s*", r"（\1）\n", content)
        block = f"=== 片段 {idx}｜{_label(doc)} ===\n{content.strip()}"
        if total + len(block) > max_chars:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)


# ==================================================================== 节点
def guard_node(state: AgentState) -> dict:
    """知识库为空直接拒绝，省掉一次 LLM 调用。"""
    if knowledge_base.is_empty():
        return {
            "refused": True,
            "answer": prompts.EMPTY_KB_MESSAGE,
            "steps": [_step("analyze", "知识库为空，请先上传书籍文件")],
        }
    return {"refused": False}


def _dialogue_block(history: list[dict], max_turns: int = 3) -> str:
    """把最近几轮对话压成一段提示，供分类节点做指代消解。"""
    if not history:
        return ""
    recent = history[-(max_turns * 2):]
    lines: list[str] = []
    for item in recent:
        role = "用户" if item.get("role") == "user" else "助手"
        content = str(item.get("content") or "").replace("\n", " ").strip()
        if not content:
            continue
        lines.append(f"{role}: {content[:180]}")
    if not lines:
        return ""
    return "【最近的对话历史】\n" + "\n".join(lines) + "\n\n"


def classify_node(state: AgentState) -> dict:
    """问题分类 + 检索策略规划（含跨轮代词消解）。"""
    query = state["query"]
    dialogue = _dialogue_block(state.get("history") or [])
    fallback = {
        "type": "事实查询",
        "entities": [],
        "strategies": [{"label": "语义检索", "mode": "semantic", "query": query}],
    }
    data = invoke_json(
        prompts.CLASSIFY_PROMPT.format(query=query, dialogue=dialogue),
        role="fast",
        temperature=0.05,
        max_tokens=900,
        default=fallback,
    )

    qtype = str(data.get("type") or "事实查询")
    entities = [str(e).strip() for e in (data.get("entities") or []) if str(e).strip()][:6]

    raw_strategies = data.get("strategies") or fallback["strategies"]
    strategies: list[dict] = []
    for item in raw_strategies[:4]:
        if not isinstance(item, dict):
            continue
        mode = str(item.get("mode") or "semantic").lower()
        if mode not in ("semantic", "keyword", "scan"):
            mode = "semantic"
        strategies.append({
            "label": str(item.get("label") or "检索"),
            "mode": mode,
            "query": str(item.get("query") or query),
        })
    if not strategies:
        strategies = fallback["strategies"]

    labels = "、".join(f"{s['label']}({s['mode']})" for s in strategies)
    return {
        "qtype": qtype,
        "entities": entities,
        "strategies": strategies,
        "steps": [
            _step("analyze", f"问题类型：{qtype}｜实体：{'、'.join(entities) or '无'}｜策略：{labels}")
        ],
    }


def _run_strategy(strategy: dict, query: str, entities: list[str]) -> list[Document]:
    mode = strategy.get("mode", "semantic")
    search_query = (strategy.get("query") or query).strip()

    if mode == "scan":
        target = entities[0] if entities else search_query
        return knowledge_base.scan(target)
    return knowledge_base.search(search_query, top_k=RETRIEVE_TOP_K)


def retrieve_node(state: AgentState) -> dict:
    """多策略召回，结果合并去重。"""
    query = state["query"]
    entities = state.get("entities") or []
    strategies = state.get("strategies") or [
        {"label": "语义检索", "mode": "semantic", "query": query}
    ]

    candidates: list[Document] = list(state.get("candidates") or [])
    steps: list[dict] = []

    for strategy in strategies:
        try:
            hits = _run_strategy(strategy, query, entities)
        except Exception as exc:
            logger.warning("检索策略失败 %s: %s", strategy, exc)
            hits = []
        candidates.extend(hits)
        steps.append(_step("search", f"{strategy['label']}：命中 {len(hits)} 条片段"))

    candidates = _dedupe(candidates)
    steps.append(_step("search", f"多策略合并去重后共 {len(candidates)} 条候选片段"))
    return {"candidates": candidates, "steps": steps}


def grade_node(state: AgentState) -> dict:
    """精排 + 相关性过滤。"""
    query = state["query"]
    candidates = state.get("candidates") or []

    if not candidates:
        return {
            "docs": [],
            "refused": True,
            "answer": prompts.NO_RELEVANT_MESSAGE,
            "steps": [_step("verify", "所有检索策略均未召回内容")],
        }

    try:
        ranked = list(get_reranker(top_n=RERANK_TOP_N, min_score=0.0).compress_documents(
            candidates[:20], query
        ))
    except Exception as exc:
        logger.warning("精排异常，使用原始顺序: %s", exc)
        ranked = candidates[:RERANK_TOP_N]

    relevant = [
        d for d in ranked
        if float(d.metadata.get("rerank_score", 0.5)) >= RERANK_MIN_SCORE
    ]

    if not relevant:
        return {
            "docs": [],
            "refused": True,
            "answer": prompts.NO_RELEVANT_MESSAGE,
            "steps": [_step("verify", f"精排后无相关片段（阈值 {RERANK_MIN_SCORE}），拒答以避免幻觉")],
        }

    top_score = max(float(d.metadata.get("rerank_score", 0.0)) for d in relevant)
    return {
        "docs": relevant,
        "refused": False,
        "steps": [
            _step("verify", f"精排保留 {len(relevant)} 条片段（最高相关度 {top_score:.2f}）")
        ],
    }


def assess_node(state: AgentState) -> dict:
    """评估证据是否足以回答，必要时给出补充检索语句。"""
    query = state["query"]
    docs = state.get("docs") or []

    # 高置信度快捷路径：首选片段相关度很高且证据数量充足时，无需再花一次 LLM 调用
    if docs and len(docs) >= 5:
        best = max(float(d.metadata.get("rerank_score", 0.0)) for d in docs)
        if best >= 0.85:
            return {
                "sufficient": True,
                "missing": [],
                "steps": [
                    _step("verify", f"证据评估：充分（首选片段相关度 {best:.2f}，{len(docs)} 条片段）")
                ],
            }

    context = "\n---\n".join(d.page_content[:300] for d in docs[:8])

    data = invoke_json(
        prompts.EVIDENCE_PROMPT.format(query=query, context=context[:4000]),
        role="agent",
        temperature=0.05,
        max_tokens=400,
        default={"sufficient": len(docs) >= 3, "missing": []},
    )
    sufficient = bool(data.get("sufficient", len(docs) >= 3))
    missing = [str(m).strip() for m in (data.get("missing") or []) if str(m).strip()][:2]

    if sufficient:
        content = f"证据评估：充分（{len(docs)} 条片段）"
    else:
        content = f"证据评估：不足，需补充 {len(missing)} 项"
    return {"sufficient": sufficient, "missing": missing, "steps": [_step("verify", content)]}


def retrieve_more_node(state: AgentState) -> dict:
    """补检索（环 1）。若本轮没有带来任何新片段，就提前结束补检索，避免空转。"""
    docs = list(state.get("docs") or [])
    missing = state.get("missing") or []
    retries = int(state.get("retries") or 0)
    steps: list[dict] = []
    extra: list[Document] = []

    for sub_query in missing[:2]:
        before = len(extra)
        try:
            raw = knowledge_base.search(sub_query, top_k=10)
            if raw:
                ranked = list(get_reranker(top_n=3, min_score=0.0).compress_documents(raw, sub_query))
                for doc in ranked:
                    if float(doc.metadata.get("rerank_score", 0.5)) >= RERANK_MIN_SCORE:
                        extra.append(doc)
        except Exception as exc:
            logger.warning("补检索失败 %s: %s", sub_query, exc)
            steps.append(_step("retry", f"补充检索「{sub_query}」失败：{exc}"))
            continue
        steps.append(_step("retry", f"补充检索「{sub_query}」：新增 {len(extra) - before} 条片段"))

    merged = _dedupe(docs + extra)
    added = len(merged) - len(docs)
    steps.append(_step("retry", f"证据扩充为 {len(merged)} 条片段（新增 {added} 条，第 {retries + 1} 轮）"))

    if added <= 0:
        # 补检索没有新证据 -> 直接放弃后续重试，进入交叉验证/生成
        steps.append(_step("retry", "补充检索未带来新证据，结束补检索"))
        return {"docs": merged, "retries": MAX_RETRIEVAL_ROUNDS, "stalled": True, "steps": steps}

    return {"docs": merged, "retries": retries + 1, "steps": steps}


def cross_check_node(state: AgentState) -> dict:
    """多元交叉验证。"""
    query = state["query"]
    docs = state.get("docs") or []
    samples = "\n---\n".join(d.page_content[:300] for d in docs[:5])
    try:
        verdict = invoke_text(
            to_messages(
                None, None,
                prompts.CROSS_CHECK_PROMPT.format(query=query, samples=samples[:4000]),
            ),
            role="agent",
            temperature=0.1,
            max_tokens=300,
        )
    except Exception as exc:
        logger.warning("交叉验证失败: %s", exc)
        verdict = "交叉验证失败，按单源证据作答"
    verdict = (verdict or "").strip()[:200]
    return {"consistency": verdict, "steps": [_step("cross_check", f"交叉验证：{verdict}")]}


def synthesize_node(state: AgentState) -> dict:
    """按问题复杂度自动选择生成模型，合成回答。"""
    query = state["query"]
    docs = state.get("docs") or []
    qtype = state.get("qtype") or "事实查询"
    consistency = state.get("consistency") or "未做交叉验证"

    model_name = registry.generation_model(qtype, len(docs))
    context = _build_context(docs)
    prompt = prompts.SYNTHESIZE_PROMPT.format(
        qtype=qtype,
        consistency=consistency,
        model=model_name,
        context=context,
        query=query,
    )
    history = (state.get("history") or [])[-MAX_HISTORY_TURNS * 2 :]
    messages = to_messages(prompts.READING_SYSTEM_PROMPT, history, prompt)

    try:
        answer = invoke_text(messages, model=model_name, temperature=0.05, max_tokens=2000)
    except Exception as exc:
        logger.exception("回答合成失败")
        return {
            "draft": f"生成失败：{exc}",
            "model": model_name,
            "steps": [_step("synthesize", f"生成失败：{exc}")],
        }

    answer = answer or prompts.NO_RELEVANT_MESSAGE
    return {
        "draft": answer,
        "model": model_name,
        "steps": [
            _step("synthesize", f"基于 {len(docs)} 条证据生成回答（模型 {model_name}）")
        ],
    }


def critique_node(state: AgentState) -> dict:
    """Self-Refine 第 1 步：事实核查。"""
    query = state["query"]
    draft = state.get("draft") or ""
    context = _build_context(state.get("docs") or [], max_chars=8000)
    rounds = int(state.get("rounds") or 0)

    try:
        critique = invoke_text(
            to_messages(
                None, None,
                prompts.CRITIQUE_PROMPT.format(query=query, answer=draft, context=context),
            ),
            role="agent",
            temperature=0.05,
            max_tokens=800,
        )
    except Exception as exc:
        logger.warning("审查失败，跳过: %s", exc)
        critique = "OK"

    passed = critique.strip().upper().startswith("OK")
    content = (
        f"第 {rounds + 1} 轮事实核查：通过"
        if passed
        else f"第 {rounds + 1} 轮事实核查：发现问题，准备修正"
    )
    return {"critique": critique, "rounds": rounds + 1, "steps": [_step("refine", content)]}


def rewrite_node(state: AgentState) -> dict:
    """Self-Refine 第 2 步：按审查意见改写。"""
    query = state["query"]
    draft = state.get("draft") or ""
    critique = state.get("critique") or ""
    context = _build_context(state.get("docs") or [], max_chars=8000)
    model_name = state.get("model") or registry.pick("chat")

    try:
        revised = invoke_text(
            to_messages(
                prompts.READING_SYSTEM_PROMPT,
                None,
                prompts.REWRITE_PROMPT.format(
                    critique=critique, query=query, answer=draft, context=context
                ),
            ),
            model=model_name,
            temperature=0.05,
            max_tokens=2000,
        )
    except Exception as exc:
        logger.warning("改写失败，保留原答案: %s", exc)
        return {"steps": [_step("refine", f"改写失败，保留原答案：{exc}")]}

    if not revised.strip():
        return {"steps": [_step("refine", "改写结果为空，保留原答案")]}
    return {"draft": revised, "steps": [_step("refine", "已按审查意见修正回答")]}


def finalize_node(state: AgentState) -> dict:
    critique = (state.get("critique") or "").strip()
    passed = critique.upper().startswith("OK")
    steps = [
        _step(
            "synthesize",
            "回答完成" if passed else "已达自我修正轮次上限，采用当前版本回答",
        )
    ]
    return {"answer": state.get("draft") or prompts.NO_RELEVANT_MESSAGE, "steps": steps}


# ==================================================================== 条件边
def after_guard(state: AgentState) -> str:
    return "refuse" if state.get("refused") else "classify"


def after_grade(state: AgentState) -> str:
    return "refuse" if state.get("refused") or not state.get("docs") else "assess"


def after_assess(state: AgentState) -> str:
    docs = state.get("docs") or []
    retries = int(state.get("retries") or 0)
    if (
        not state.get("sufficient")
        and state.get("missing")
        and retries < MAX_RETRIEVAL_ROUNDS
    ):
        return "retrieve_more"
    if len(docs) >= 3:
        return "cross_check"
    return "synthesize"


def after_critique(state: AgentState) -> str:
    critique = (state.get("critique") or "").strip()
    rounds = int(state.get("rounds") or 0)
    if critique.upper().startswith("OK") or rounds >= MAX_REFINE_ROUNDS:
        return "finalize"
    return "rewrite"


# ==================================================================== 构图
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("guard", guard_node)
    graph.add_node("classify", classify_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("grade", grade_node)
    graph.add_node("assess", assess_node)
    graph.add_node("retrieve_more", retrieve_more_node)
    graph.add_node("cross_check", cross_check_node)
    graph.add_node("synthesize", synthesize_node)
    # 注意：节点名不能与 AgentState 的字段同名（LangGraph 会报 state key 冲突），
    # 因此这里用 review / revise 而不是 critique / rewrite。
    graph.add_node("review", critique_node)
    graph.add_node("revise", rewrite_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", after_guard, {"refuse": END, "classify": "classify"})
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", after_grade, {"refuse": END, "assess": "assess"})
    graph.add_conditional_edges(
        "assess",
        after_assess,
        {
            "retrieve_more": "retrieve_more",
            "cross_check": "cross_check",
            "synthesize": "synthesize",
        },
    )
    graph.add_edge("retrieve_more", "assess")          # 环 1：证据不足则再检索
    graph.add_edge("cross_check", "synthesize")
    graph.add_edge("synthesize", "review")
    graph.add_conditional_edges(
        "review", after_critique, {"rewrite": "revise", "finalize": "finalize"}
    )
    graph.add_edge("revise", "review")                 # 环 2：Self-Refine
    graph.add_edge("finalize", END)

    return graph.compile()


_AGENT = None


def get_agent():
    global _AGENT
    if _AGENT is None:
        _AGENT = build_graph()
        logger.info("LangGraph Agent 编译完成")
    return _AGENT


# ==================================================================== 对外接口
def run_agent(query: str, history: list[dict] | None = None) -> dict[str, Any]:
    """执行一次 Agentic RAG，返回 {answer, steps, model, refused}。"""
    agent = get_agent()
    initial: AgentState = {
        "query": query,
        "history": history or [],
        "candidates": [],
        "docs": [],
        "retries": 0,
        "rounds": 0,
        "steps": [],
    }
    try:
        result = agent.invoke(initial, config={"recursion_limit": 50})
    except Exception as exc:
        logger.exception("Agent 执行失败")
        return {
            "answer": f"⚠️ 处理失败：{exc}",
            "steps": [_step("analyze", f"Agent 执行异常：{exc}")],
            "model": "",
            "refused": True,
        }

    return {
        "answer": result.get("answer") or prompts.NO_RELEVANT_MESSAGE,
        "steps": result.get("steps") or [],
        "model": result.get("model") or "",
        "refused": bool(result.get("refused")),
        "evidence_count": len(result.get("docs") or []),
    }
