"""离线自检：不启动服务，验证各模块能否正常构建。"""
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

FAILED = 0


def stage(name):
    def deco(fn):
        def wrapper():
            global FAILED
            try:
                detail = fn()
                print(f"[ OK ] {name}" + (f" :: {detail}" if detail else ""))
            except Exception:
                FAILED += 1
                print(f"[FAIL] {name}")
                traceback.print_exc()
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


@stage("import config")
def t1():
    import config
    return f"base={config.DASHSCOPE_BASE_URL}"


@stage("model registry (network)")
def t2():
    from models import registry
    available = registry.refresh(force=True)
    resolved = registry.resolve_all()
    print("        available:", len(available))
    for role, model in resolved.items():
        print(f"        {role:<10} -> {model}")
    return resolved["chat"]


@stage("langchain splitter (chapter aware)")
def t3():
    from knowledge.splitter import ChapterAwareTextSplitter
    splitter = ChapterAwareTextSplitter(chunk_size=300)
    text = (
        "第一回 甄士隐梦幻识通灵\n\n"
        + "此开卷第一回也。作者自云：因曾历过一番梦幻之后，故将真事隐去。" * 6
        + "\n\n第二回 贾夫人仙逝扬州城\n\n"
        + "诗云：一局输赢料不真，香销茶尽尚逡巡。" * 6
    )
    chunks = splitter.split_text(text)
    assert len(chunks) >= 2, chunks
    docs = splitter.split_documents([])
    assert docs == []
    print("        chunks:", len(chunks))
    print("        first:", chunks[0][:60].replace("\n", " "))
    return f"{len(chunks)} chunks, min_chars={splitter.min_chunk_chars}"


@stage("embeddings (network)")
def t4():
    from knowledge.embeddings import get_embeddings
    emb = get_embeddings()
    vectors = emb.embed_documents(["人工智能是什么", "机器学习"])
    print("        dim:", len(vectors[0]), "count:", len(vectors))
    return f"dim={len(vectors[0])}"


@stage("reranker (network)")
def t5():
    from langchain_core.documents import Document
    from knowledge.rerank import get_reranker
    docs = [
        Document(page_content="林黛玉多愁善感，心思细腻。"),
        Document(page_content="薛宝钗端庄大方。"),
        Document(page_content="贾宝玉衔玉而生。"),
    ]
    ranked = get_reranker(top_n=3).compress_documents(docs, "林黛玉的性格")
    for d in ranked:
        print(f"        {d.metadata['rerank_score']:.3f} {d.page_content[:20]}")
    return f"{len(ranked)} ranked"


@stage("knowledge base add/search (network)")
def t6():
    from knowledge.store import HybridKnowledgeBase
    import tempfile

    kb = HybridKnowledgeBase(Path(tempfile.mkdtemp(prefix="kb_test_")))
    tmpfile = Path(tempfile.mkdtemp(prefix="kb_doc_")) / "测试书.txt"
    tmpfile.write_text(
        "第一回 甄士隐梦幻识通灵\n\n"
        "甄士隐梦中见一僧一道，谈及通灵宝玉。甄士隐醒来，抱女儿英莲上街看花灯。\n\n"
        "第二回 贾夫人仙逝扬州城\n\n"
        "林黛玉之母贾敏病逝，贾雨村受聘为黛玉之师。冷子兴演说荣国府。\n\n"
        "第三回 贾雨村夤缘复旧职 林黛玉抛父进京都\n\n"
        "林黛玉进贾府，初见贾宝玉，宝玉道：这个妹妹我曾见过的。\n",
        encoding="utf-8",
    )
    info = kb.add_file(tmpfile, source_name="测试书.txt")
    print("        add:", info)
    hits = kb.search("林黛玉第一次出场", top_k=5)
    for h in hits:
        print(f"        {h.metadata.get('score')} | {h.page_content[:40]}")
    stats = kb.stats()
    preview = kb.preview("测试书.txt")
    scan = kb.scan("林黛玉")
    assert kb.delete_source("测试书.txt")
    assert kb.stats()["total_chunks"] == 0
    return f"chunks={info['chunks']} scan={len(scan)} preview={len(preview)}"


@stage("asr (network)")
def t7():
    from speech.asr import transcribe_file
    audio = ROOT / "test_audio" / "林黛玉是谁.mp3"
    result = transcribe_file(audio)
    print("        ", result)
    return result["text"]


@stage("audio pipeline")
def t8():
    from speech.preprocess import process_audio_pipeline
    audio = ROOT / "test_audio" / "林黛玉是谁.mp3"
    result = process_audio_pipeline(audio)
    assert result["waveform_image"], "waveform empty"
    assert result["mfcc_image"], "mfcc empty"
    print("        duration:", result["original_duration"], "mfcc:", result["mfcc_shape"])
    return f"waveform={len(result['waveform_image'])}B mfcc={len(result['mfcc_image'])}B"


@stage("langgraph compile")
def t9():
    from graph import build_graph
    graph = build_graph()
    nodes = sorted(graph.get_graph().nodes.keys())
    print("        nodes:", nodes)
    return f"{len(nodes)} nodes"


def main():
    print("=" * 70)
    print("BookBuddy 离线自检")
    print("=" * 70)
    for fn in (t1, t2, t3, t4, t5, t6, t7, t8, t9):
        fn()
    print("=" * 70)
    print("FAILED:", FAILED)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
