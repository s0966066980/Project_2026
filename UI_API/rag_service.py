import gc
import json
import os
import re
import shutil
import uuid
import warnings
import math
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

import config

warnings.filterwarnings(
    "ignore",
    message=r"The class `Chroma` was deprecated.*",
    category=Warning,
)
try:
    from langchain_core._api.deprecation import LangChainDeprecationWarning

    warnings.filterwarnings("ignore", category=LangChainDeprecationWarning)
except Exception:
    pass

try:
    from langchain_community.vectorstores import Chroma
    try:
        from langchain_ollama import OllamaEmbeddings
    except Exception:
        from langchain_community.embeddings import OllamaEmbeddings
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_core.documents import Document
except Exception:  # pragma: no cover - handled by runtime fallback
    Chroma = None
    OllamaEmbeddings = None
    HuggingFaceEmbeddings = None
    Document = None

try:
    from langchain_community.document_loaders import PyPDFLoader
except Exception:  # pragma: no cover
    PyPDFLoader = None

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:  # pragma: no cover
    RecursiveCharacterTextSplitter = None

try:
    from sentence_transformers import CrossEncoder
except Exception:  # pragma: no cover
    CrossEncoder = None

try:
    import ai_services
except Exception:  # pragma: no cover
    ai_services = None


@dataclass
class RagChunk:
    chunk_id: str
    content: str
    metadata: dict
    score: float = 0.0
    source: str = ""


_vectorstore = None
_embeddings = None
_embedding_provider = ""
_rag_ready = False
_chunk_cache: list[RagChunk] = []
_bm25_index = None
_bm25_tokens: list[list[str]] = []
_reranker = None
_reranker_failed = False
_last_retrieval = {}


def _now_iso():
    return datetime.now().isoformat()


def _rag_settings() -> dict:
    defaults = {
        "use_multi_query": True,
        "use_hybrid_search": True,
        "use_reranker": True,
        "use_context_compression": True,
        "use_answer_evaluation": True,
        "strict_grounding": True,
        "answer_verification": True,
        "fail_closed_on_eval_error": True,
        "min_retrieval_score": 0.08,
        "min_keyword_overlap": 1,
        "max_answer_chars": 420,
        "top_k_vector": 10,
        "top_k_keyword": 10,
        "top_k_final": 5,
        "context_max_chars": 2600,
        "chunk_size": 700,
        "chunk_overlap": 120,
        "embedding_model": "nomic-embed-text",
        "embedding_provider": "ollama",
        "reranker_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    }
    loaded = config.get("rag", {}) or {}
    if not isinstance(loaded, dict):
        loaded = {}
    merged = {**defaults, **loaded}
    try:
        merged["top_k_final"] = int(merged.get("top_k_final") or config.get("RAG_TOP_K", 5))
    except Exception:
        merged["top_k_final"] = int(config.get("RAG_TOP_K", 5))
    return merged


def ensure_writable_tree(path: str):
    if not os.path.exists(path):
        return
    for root, dirs, files in os.walk(path):
        try:
            os.chmod(root, 0o775)
        except OSError:
            pass
        for name in dirs:
            try:
                os.chmod(os.path.join(root, name), 0o775)
            except OSError:
                pass
        for name in files:
            try:
                os.chmod(os.path.join(root, name), 0o664)
            except OSError:
                pass


def vector_db_parent_dir() -> str:
    base_dir = os.path.dirname(config.VECTOR_DB_DIR) or "."
    return os.path.join(base_dir, "chroma_db_versions")


def has_chroma_db(path: str) -> bool:
    return bool(path) and os.path.exists(os.path.join(path, "chroma.sqlite3"))


def read_vector_meta() -> dict:
    try:
        with open(config.RAG_VECTOR_META_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_vector_meta(active_dir: str, embedding_key: str = ""):
    os.makedirs(config.LEARNING_DATA_DIR, exist_ok=True)
    with open(config.RAG_VECTOR_META_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "active_dir": active_dir,
            "embedding_key": embedding_key or _embedding_provider,
            "updated_at": _now_iso()
        }, f, ensure_ascii=False, indent=4)


def active_vector_db_dir() -> str:
    meta_dir = read_vector_meta().get("active_dir", "")
    if has_chroma_db(meta_dir):
        return meta_dir
    if has_chroma_db(config.VECTOR_DB_DIR):
        return config.VECTOR_DB_DIR
    return config.VECTOR_DB_DIR


def new_vector_db_dir() -> str:
    parent = vector_db_parent_dir()
    os.makedirs(parent, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(parent, f"rag_{stamp}_{uuid.uuid4().hex[:8]}")


def cleanup_old_vector_dbs(active_dir: str, keep: int = 3):
    parent = vector_db_parent_dir()
    if not os.path.isdir(parent):
        return
    candidates = []
    for name in os.listdir(parent):
        path = os.path.join(parent, name)
        if os.path.isdir(path) and os.path.abspath(path) != os.path.abspath(active_dir):
            candidates.append((os.path.getmtime(path), path))
    for _, path in sorted(candidates, reverse=True)[keep:]:
        try:
            ensure_writable_tree(path)
            shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass


def release():
    global _vectorstore, _rag_ready
    if _vectorstore is not None:
        try:
            client = getattr(_vectorstore, "_client", None)
            if client and hasattr(client, "reset"):
                client.reset()
        except Exception:
            pass
    _vectorstore = None
    _rag_ready = False
    gc.collect()


def clear_vector_storage():
    release()
    for path in [config.VECTOR_DB_DIR, vector_db_parent_dir()]:
        try:
            if os.path.isdir(path):
                ensure_writable_tree(path)
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass


def _ollama_base_url() -> str:
    parsed = urlsplit(config.OLLAMA_API_URL)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "http://localhost:11434"


def _get_embeddings():
    global _embeddings, _embedding_provider
    settings = _rag_settings()
    provider = str(settings.get("embedding_provider") or "ollama").lower()
    model = settings.get("embedding_model") or "nomic-embed-text"
    key = f"{provider}:{model}"
    if _embeddings is not None and _embedding_provider == key:
        return _embeddings

    if provider == "ollama" and OllamaEmbeddings is not None:
        try:
            _embeddings = OllamaEmbeddings(model=model, base_url=_ollama_base_url())
            _embedding_provider = key
            return _embeddings
        except Exception as e:
            print(f"⚠️ Ollama embedding 初始化失敗，改用 HuggingFace embeddings: {e}")

    if HuggingFaceEmbeddings is None:
        raise RuntimeError("No embedding backend available.")
    _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    _embedding_provider = "huggingface:all-MiniLM-L6-v2"
    return _embeddings


def _split_text(text: str, metadata: dict, chunk_prefix: str) -> list[RagChunk]:
    settings = _rag_settings()
    clean = (text or "").strip()
    if not clean:
        return []

    chunks = []
    if RecursiveCharacterTextSplitter:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=int(settings.get("chunk_size", 700)),
            chunk_overlap=int(settings.get("chunk_overlap", 120)),
            separators=["\n\n", "\n", "。", "，", " ", ""],
        )
        parts = splitter.split_text(clean)
    else:
        size = int(settings.get("chunk_size", 700))
        overlap = int(settings.get("chunk_overlap", 120))
        parts = []
        step = max(1, size - overlap)
        for start in range(0, len(clean), step):
            parts.append(clean[start:start + size])

    for idx, part in enumerate(parts):
        chunk_id = f"{chunk_prefix}_chunk_{idx + 1}"
        chunk_meta = {
            **metadata,
            "chunk_id": chunk_id,
            "chunk_index": idx + 1,
        }
        chunks.append(RagChunk(chunk_id=chunk_id, content=part.strip(), metadata=chunk_meta))
    return chunks


def rag_docs_to_chunks(rag_docs: list[dict]) -> list[RagChunk]:
    chunks = []
    for doc in rag_docs:
        text = doc.get("reviewed_text") or doc.get("source_text") or ""
        metadata = dict(doc.get("metadata") or {})
        source_type = doc.get("source_type", "manual")
        source_id = doc.get("source_id", "")
        metadata.update({
            "doc_id": doc.get("id"),
            "source_type": source_type,
            "source_id": source_id,
            "file_name": metadata.get("file_name") or f"{source_type}/{source_id}",
            "page": metadata.get("page", "-"),
        })
        chunks.extend(_split_text(text, metadata, str(doc.get("id") or source_id or uuid.uuid4().hex)))
    return chunks


def chunks_to_documents(chunks: list[RagChunk]) -> list:
    if Document is None:
        return []
    return [Document(page_content=chunk.content, metadata=chunk.metadata) for chunk in chunks]


def _tokenize(text: str) -> list[str]:
    lowered = str(text or "").lower()
    latin = re.findall(r"[a-z0-9_]+", lowered)
    cjk = re.findall(r"[\u4e00-\u9fff]", lowered)
    cjk_bigrams = [cjk[i] + cjk[i + 1] for i in range(max(0, len(cjk) - 1))]
    return latin + cjk + cjk_bigrams


def _build_bm25(chunks: list[RagChunk]):
    global _bm25_index, _bm25_tokens
    _bm25_tokens = [_tokenize(chunk.content) for chunk in chunks]
    _bm25_index = {
        "doc_freq": {},
        "avgdl": sum(len(tokens) for tokens in _bm25_tokens) / max(1, len(_bm25_tokens)),
        "doc_count": len(_bm25_tokens),
    }
    for tokens in _bm25_tokens:
        for token in set(tokens):
            _bm25_index["doc_freq"][token] = _bm25_index["doc_freq"].get(token, 0) + 1


def init(rag_docs: list[dict], force_rebuild: bool = False):
    global _vectorstore, _rag_ready, _chunk_cache, _embeddings, _embedding_provider
    if Chroma is None:
        raise RuntimeError("langchain Chroma is not available.")

    chunks = rag_docs_to_chunks(rag_docs)
    if not chunks:
        chunks = [RagChunk(
            chunk_id="empty_chunk_1",
            content="目前沒有可用的 RAG 補充文本。",
            metadata={"chunk_id": "empty_chunk_1", "file_name": "empty", "page": "-"},
        )]
    _chunk_cache = chunks
    _build_bm25(chunks)

    active_dir = active_vector_db_dir()
    has_persisted = has_chroma_db(active_dir)
    embedding_model = _get_embeddings()
    active_meta = read_vector_meta()
    has_matching_embedding = active_meta.get("embedding_key") == _embedding_provider
    if has_persisted and not force_rebuild and has_matching_embedding:
        _vectorstore = Chroma(
            persist_directory=active_dir,
            embedding_function=embedding_model
        )
        _rag_ready = True
        print(f"✅ RAG System ready. Loaded persisted Chroma DB: {active_dir}")
        return

    docs = chunks_to_documents(chunks)
    build_dir = new_vector_db_dir() if force_rebuild else active_dir
    try:
        _vectorstore = Chroma.from_documents(
            documents=docs,
            embedding=embedding_model,
            persist_directory=build_dir
        )
    except Exception as e:
        print(f"⚠️ 向量庫使用目前 embedding 建立失敗，改用 HuggingFace embeddings: {e}")
        _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        _embedding_provider = "huggingface:all-MiniLM-L6-v2"
        _vectorstore = Chroma.from_documents(
            documents=docs,
            embedding=_embeddings,
            persist_directory=build_dir
        )
    write_vector_meta(build_dir, _embedding_provider)
    _rag_ready = True
    cleanup_old_vector_dbs(build_dir)
    gc.collect()
    print(f"✅ RAG System ready. Rebuilt {len(chunks)} chunks: {build_dir}")


def _vector_search(query: str, top_k: int) -> list[RagChunk]:
    if not _vectorstore:
        return []
    try:
        if hasattr(_vectorstore, "similarity_search_with_score"):
            pairs = _vectorstore.similarity_search_with_score(query, k=top_k)
            return [
                RagChunk(
                    chunk_id=str(doc.metadata.get("chunk_id") or doc.metadata.get("id") or idx),
                    content=doc.page_content,
                    metadata=dict(doc.metadata),
                    score=1.0 / (1.0 + max(0.0, float(distance or 0.0))),
                    source="vector",
                )
                for idx, (doc, distance) in enumerate(pairs)
            ]
        docs = _vectorstore.similarity_search(query, k=top_k)
        return [
            RagChunk(
                chunk_id=str(doc.metadata.get("chunk_id") or doc.metadata.get("id") or idx),
                content=doc.page_content,
                metadata=dict(doc.metadata),
                score=1.0 / (idx + 1),
                source="vector",
            )
            for idx, doc in enumerate(docs)
        ]
    except Exception as e:
        print(f"⚠️ Vector search failed: {e}")
        return []


def _bm25_score(query_tokens: list[str], doc_tokens: list[str]) -> float:
    if not query_tokens or not doc_tokens or not _bm25_index:
        return 0.0
    score = 0.0
    k1 = 1.5
    b = 0.75
    avgdl = float(_bm25_index.get("avgdl") or 1.0)
    doc_count = int(_bm25_index.get("doc_count") or 1)
    doc_len = len(doc_tokens)
    tf_counts = {}
    for token in doc_tokens:
        tf_counts[token] = tf_counts.get(token, 0) + 1
    for token in query_tokens:
        tf = tf_counts.get(token, 0)
        if tf <= 0:
            continue
        df = int((_bm25_index.get("doc_freq") or {}).get(token, 0))
        idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
        score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avgdl)))
    return score


def _keyword_search(query: str, top_k: int) -> list[RagChunk]:
    tokens = _tokenize(query)
    scored = []
    for idx, chunk in enumerate(_chunk_cache):
        score = _bm25_score(tokens, _bm25_tokens[idx] if idx < len(_bm25_tokens) else [])
        if score > 0:
            scored.append(RagChunk(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                metadata=dict(chunk.metadata),
                score=score,
                source="keyword",
            ))
    return sorted(scored, key=lambda row: row.score, reverse=True)[:top_k]


def _merge_results(groups: list[list[RagChunk]]) -> list[RagChunk]:
    merged = {}
    for group in groups:
        for rank, chunk in enumerate(group):
            key = chunk.chunk_id or f"{chunk.metadata.get('doc_id')}:{chunk.content[:32]}"
            reciprocal = 1.0 / (60 + rank + 1)
            if key not in merged:
                merged[key] = RagChunk(
                    chunk_id=chunk.chunk_id,
                    content=chunk.content,
                    metadata=dict(chunk.metadata),
                    score=0.0,
                    source=chunk.source,
                )
            merged[key].score += reciprocal + max(0.0, float(chunk.score or 0.0)) * 0.01
            if chunk.source not in merged[key].source:
                merged[key].source = ",".join(part for part in [merged[key].source, chunk.source] if part)
    return sorted(merged.values(), key=lambda row: row.score, reverse=True)


def _generate_multi_queries(question: str) -> list[str]:
    settings = _rag_settings()
    if not settings.get("use_multi_query", True) or ai_services is None:
        return [question]
    system_prompt = (
        "你是本地 RAG 查詢改寫器。請根據使用者問題產生 3 個語意不同但目標一致的檢索查詢。"
        "不要回答問題，只輸出 JSON：{\"queries\":[\"查詢1\",\"查詢2\",\"查詢3\"]}"
    )
    user_prompt = f"使用者問題：{question}"
    try:
        result = ai_services.ask_ollama(system_prompt, user_prompt, "RAG_MULTI_QUERY")
        queries = result.get("queries", []) if isinstance(result, dict) else []
        queries = [str(q).strip() for q in queries if str(q).strip()]
        return [question] + queries[:3]
    except Exception:
        return [question]


def _load_reranker():
    global _reranker, _reranker_failed
    settings = _rag_settings()
    if not settings.get("use_reranker", True) or _reranker_failed or CrossEncoder is None:
        return None
    if _reranker is not None:
        return _reranker
    try:
        _reranker = CrossEncoder(settings.get("reranker_model") or "cross-encoder/ms-marco-MiniLM-L-6-v2")
        return _reranker
    except Exception as e:
        _reranker_failed = True
        print(f"⚠️ Reranker unavailable, fallback to retrieval scores: {e}")
        return None


def _rerank(question: str, chunks: list[RagChunk]) -> list[RagChunk]:
    reranker = _load_reranker()
    if not reranker or not chunks:
        return chunks
    try:
        scores = reranker.predict([(question, chunk.content) for chunk in chunks])
        for chunk, score in zip(chunks, scores):
            chunk.score = float(score)
            chunk.source = ",".join(part for part in [chunk.source, "rerank"] if part)
        return sorted(chunks, key=lambda row: row.score, reverse=True)
    except Exception as e:
        print(f"⚠️ Reranker failed, fallback to retrieval scores: {e}")
        return chunks


def _compress(question: str, chunks: list[RagChunk]) -> list[RagChunk]:
    settings = _rag_settings()
    if not settings.get("use_context_compression", True):
        return chunks[:int(settings.get("top_k_final", 5))]
    query_tokens = set(_tokenize(question))
    max_chars = int(settings.get("context_max_chars", 2600))
    selected = []
    used = 0
    for chunk in chunks:
        content = chunk.content.strip()
        overlap = len(query_tokens & set(_tokenize(content)))
        if query_tokens and overlap == 0 and selected:
            continue
        if used + len(content) > max_chars and selected:
            continue
        selected.append(chunk)
        used += len(content)
        if len(selected) >= int(settings.get("top_k_final", 5)):
            break
    return selected or chunks[:int(settings.get("top_k_final", 5))]


def _evaluate_answerability(question: str, chunks: list[RagChunk]) -> dict:
    settings = _rag_settings()
    if not settings.get("use_answer_evaluation", True) or ai_services is None:
        return {"sufficient": True, "reason": "evaluation_disabled"}
    context = "\n\n".join(chunk.content[:700] for chunk in chunks)
    if not context.strip():
        return {"sufficient": False, "reason": "no_context"}
    system_prompt = (
        "你是 RAG 檢索品質評估器。判斷 retrieved context 是否足以回答使用者問題。"
        "只輸出 JSON：{\"sufficient\":true,\"reason\":\"簡短原因\"}"
    )
    user_prompt = f"問題：{question}\n\nretrieved context:\n{context}"
    try:
        result = ai_services.ask_ollama(system_prompt, user_prompt, "RAG_EVAL")
        sufficient = bool(result.get("sufficient", True)) if isinstance(result, dict) else True
        return {"sufficient": sufficient, "reason": str(result.get("reason", "")) if isinstance(result, dict) else ""}
    except Exception:
        if settings.get("fail_closed_on_eval_error", True):
            return {"sufficient": False, "reason": "evaluation_failed_closed"}
        else:
            return {"sufficient": True, "reason": "evaluation_failed_open"}

def _retrieval_quality_gate(question: str, chunks: list[RagChunk]) -> dict:
    settings = _rag_settings()
    if not chunks:
        return {"sufficient": False, "reason": "no_chunks"}
    
    max_score = max((float(chunk.score or 0.0) for chunk in chunks), default=0.0)
    min_retrieval_score = float(settings.get("min_retrieval_score", 0.08))
    min_keyword_overlap = int(settings.get("min_keyword_overlap", 1))
    
    query_tokens = set(_tokenize(question))
    max_overlap = 0
    for chunk in chunks:
        overlap = len(query_tokens & set(_tokenize(chunk.content)))
        if overlap > max_overlap:
            max_overlap = overlap
            
    if max_score < min_retrieval_score and max_overlap < min_keyword_overlap:
        return {"sufficient": False, "reason": "low_score_and_overlap"}
        
    return {"sufficient": True, "reason": "ok"}

def verify_answer_grounding(question: str, answer: str, context: str) -> dict:
    if ai_services is None:
        return {"grounded": True, "unsupported_claims": [], "safe_answer": answer}
        
    system_prompt = (
        "你是 RAG 答案驗證器。只判斷回答是否完全被 context 支持。\n"
        "若回答中有 context 沒有的價格、政策、設定、活動、模型名稱、數字，grounded=false。\n"
        "safe_answer 必須是繁體中文短句：「目前文件沒有足夠資訊回答，請新增對應 RAG 文件或確認設定。」或只保留 context 支持的內容。\n"
        "輸出 JSON：\n"
        "{\n"
        "  \"grounded\": true/false,\n"
        "  \"unsupported_claims\": [],\n"
        "  \"safe_answer\": \"若不支持，改寫成保守回答\"\n"
        "}"
    )
    user_prompt = f"問題：{question}\n\n回答：{answer}\n\nContext:\n{context}"
    try:
        # Use low temperature for verification
        result = ai_services.ask_llm(system_prompt, user_prompt, "RAG_VERIFY", temperature=0.1)
        if isinstance(result, dict) and "grounded" in result:
            return result
        return {"grounded": True, "unsupported_claims": [], "safe_answer": answer}
    except Exception:
        # Fail open on verification error
        return {"grounded": True, "unsupported_claims": [], "safe_answer": answer}

def is_context_sufficient(retrieval_details: dict) -> bool:
    if not retrieval_details:
        return False
    eval_ok = retrieval_details.get("evaluation", {}).get("sufficient", True)
    gate_ok = retrieval_details.get("quality_gate", {}).get("sufficient", True)
    return eval_ok and gate_ok


def _citation_for(chunk: RagChunk) -> dict:
    meta = chunk.metadata or {}
    return {
        "file_name": str(meta.get("file_name") or meta.get("source_id") or "rag_docs"),
        "page": meta.get("page", "-"),
        "chunk_id": str(meta.get("chunk_id") or chunk.chunk_id),
        "source_type": meta.get("source_type", ""),
        "source_id": meta.get("source_id", ""),
    }


def format_context(chunks: list[RagChunk], evaluation: dict) -> str:
    if evaluation and evaluation.get("sufficient") is False:
        return "【RAG 檢索評估】目前文件沒有足夠資訊回答這個問題，請不要臆測。"
    lines = ["【RAG 檢索補充】"]
    for idx, chunk in enumerate(chunks, 1):
        citation = _citation_for(chunk)
        lines.append(
            f"來源 {idx}: file_name={citation['file_name']} page={citation['page']} chunk_id={citation['chunk_id']}\n"
            f"{chunk.content}"
        )
    if chunks:
        lines.append("【引用規則】若回答引用 RAG 補充內容，請顯示來源 file_name、page、chunk_id。")
    return "\n\n".join(lines)


def retrieve(question: str, emotion_desc: str = "") -> dict:
    global _last_retrieval
    settings = _rag_settings()
    query = f"{question} {emotion_desc}".strip()
    queries = _generate_multi_queries(query)
    result_groups = []
    for q in queries:
        if settings.get("use_hybrid_search", True):
            result_groups.append(_vector_search(q, int(settings.get("top_k_vector", 10))))
            result_groups.append(_keyword_search(q, int(settings.get("top_k_keyword", 10))))
        else:
            result_groups.append(_vector_search(q, int(settings.get("top_k_final", 5))))
    merged = _merge_results(result_groups)
    ranked = _rerank(query, merged)
    compressed = _compress(query, ranked)
    quality_gate = _retrieval_quality_gate(query, compressed)
    evaluation = _evaluate_answerability(query, compressed)
    
    if not quality_gate["sufficient"]:
        evaluation["sufficient"] = False
        evaluation["reason"] = quality_gate["reason"]
        
    context = format_context(compressed, evaluation)
    citations = [_citation_for(chunk) for chunk in compressed]
    _last_retrieval = {
        "question": question,
        "queries": queries,
        "citations": citations,
        "evaluation": evaluation,
        "quality_gate": quality_gate,
        "settings": settings,
    }
    return _last_retrieval | {"context": context, "chunks": compressed}


def get_last_retrieval() -> dict:
    return dict(_last_retrieval or {})


def load_pdf_chunks(file_path: str, file_name: str = "") -> list[dict]:
    if PyPDFLoader is None:
        raise RuntimeError("PyPDFLoader unavailable. Install pypdf and langchain-community.")
    loader = PyPDFLoader(file_path)
    pages = loader.load()
    output = []
    for page_index, page in enumerate(pages):
        metadata = dict(page.metadata or {})
        metadata["file_name"] = file_name or os.path.basename(file_path)
        metadata["page"] = metadata.get("page", page_index + 1)
        chunks = _split_text(page.page_content or "", metadata, f"pdf_{uuid.uuid4().hex}")
        for chunk in chunks:
            output.append({
                "text": chunk.content,
                "metadata": chunk.metadata,
            })
    return output
