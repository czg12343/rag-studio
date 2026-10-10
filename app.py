from __future__ import annotations

import os
import re
from html import escape
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

try:
    from modules.document_loader import SUPPORTED_EXTENSIONS, load_document
    from modules.history import clear_history, init_db, list_history, save_record
    from modules.rag_chain import RagAnswer, answer_question
    from modules.text_splitter import split_text
    from modules.vector_store import delete_source, index_documents, list_indexed_sources
    from modules.uploads import ingest_bytes
except ModuleNotFoundError as exc:
    st.set_page_config(page_title="智能文档问答与知识库系统", layout="wide")
    st.error(f"缺少 Python 依赖：{exc.name}")
    st.code("python -m pip install -r requirements.txt", language="bash")
    st.stop()


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    st.set_page_config(page_title="智能文档问答与知识库系统", layout="wide")
    _inject_styles()
    init_db()
    _init_state()

    sources = list_indexed_sources()
    _render_header(sources)
    options = _render_sidebar(sources)

    qa_tab, kb_tab, history_tab = st.tabs(["智能问答", "知识库管理", "历史记录"])
    with qa_tab:
        _render_qa_panel(sources, options)
    with kb_tab:
        _render_source_panel(sources)
    with history_tab:
        _render_history_panel()


def _init_state() -> None:
    st.session_state.setdefault("last_answer", None)
    st.session_state.setdefault("last_preview", "")
    st.session_state.setdefault("last_index_report", "")


def _render_header(sources: list[dict[str, int | str]]) -> None:
    total_sources = len(sources)
    total_chunks = sum(int(item.get("chunks", 0)) for item in sources)
    total_pages = sum(int(item.get("pages", 0)) for item in sources)
    last_answer: RagAnswer | None = st.session_state.get("last_answer")
    confidence = _confidence_label(last_answer.confidence) if last_answer else "待生成"

    st.markdown(
        f"""
        <div class="app-hero">
            <div>
                <h1 class="app-title">智能文档问答工作台</h1>
                <p class="app-subtitle">面向论文、报告和业务文档的本地知识库检索与可信问答。</p>
            </div>
            <div class="hero-badge">Hybrid RAG 已启用</div>
        </div>
        <div class="stat-grid">
            <div class="stat-card">
                <div class="stat-label">已索引文档</div>
                <div class="stat-value">{total_sources}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">知识片段</div>
                <div class="stat-value">{total_chunks}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">识别页数</div>
                <div class="stat-value">{total_pages}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">最近回答检索启发式等级</div>
                <div class="stat-value">{confidence}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --app-bg: #f6f7f9;
            --panel: #ffffff;
            --panel-soft: #f9fafb;
            --line: #dfe4ea;
            --text: #172033;
            --muted: #667085;
            --accent: #2563eb;
            --accent-2: #0f766e;
            --warning: #b45309;
        }

        .stApp {
            background: var(--app-bg);
            color: var(--text);
        }

        .block-container {
            max-width: 1400px;
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }

        section[data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--line);
        }

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: var(--text);
            letter-spacing: 0;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px;
            border-color: var(--line);
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
            border-bottom: 1px solid var(--line);
        }

        .stTabs [data-baseweb="tab"] {
            height: 42px;
            padding: 0 16px;
            border-radius: 8px 8px 0 0;
            color: var(--muted);
            font-weight: 600;
        }

        .stTabs [aria-selected="true"] {
            background: #ffffff;
            color: var(--accent);
            border: 1px solid var(--line);
            border-bottom-color: #ffffff;
        }

        .stButton > button {
            border-radius: 8px;
            font-weight: 650;
            border: 1px solid var(--line);
        }

        .stButton > button[kind="primary"] {
            background: var(--accent);
            border-color: var(--accent);
        }

        div[data-testid="stTextArea"] textarea,
        div[data-testid="stSelectbox"] > div,
        div[data-testid="stNumberInput"] input {
            border-radius: 8px;
        }

        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 14px 16px;
        }

        .app-hero {
            display: flex;
            align-items: stretch;
            justify-content: space-between;
            gap: 18px;
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 20px 22px;
            margin-bottom: 16px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
        }

        .app-title {
            margin: 0;
            font-size: 28px;
            line-height: 1.25;
            letter-spacing: 0;
            color: var(--text);
        }

        .app-subtitle {
            margin: 8px 0 0;
            color: var(--muted);
            font-size: 14px;
        }

        .hero-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            height: 30px;
            padding: 0 10px;
            border-radius: 8px;
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #bbf7d0;
            font-size: 13px;
            font-weight: 700;
            white-space: nowrap;
        }

        .stat-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-bottom: 18px;
        }

        .stat-card {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 14px 16px;
        }

        .stat-label {
            color: var(--muted);
            font-size: 12px;
            font-weight: 650;
        }

        .stat-value {
            color: var(--text);
            font-size: 24px;
            line-height: 1.2;
            font-weight: 760;
            margin-top: 5px;
        }

        .panel {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 18px;
            min-height: 100%;
        }

        .panel-title {
            font-size: 16px;
            font-weight: 750;
            color: var(--text);
            margin: 0 0 12px;
        }

        .answer-box {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 16px 18px;
            margin-top: 12px;
        }

        .rewrite-box {
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            color: #1e3a8a;
            border-radius: 8px;
            padding: 10px 12px;
            margin: 12px 0;
            font-size: 13px;
        }

        .empty-box {
            background: #ffffff;
            border: 1px dashed #cbd5e1;
            border-radius: 8px;
            padding: 28px;
            color: var(--muted);
            text-align: center;
        }

        .citation-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            color: var(--text);
            font-weight: 700;
        }

        .pill {
            display: inline-flex;
            align-items: center;
            min-height: 24px;
            padding: 2px 8px;
            border-radius: 8px;
            background: #f1f5f9;
            color: #475569;
            font-size: 12px;
            font-weight: 650;
        }

        .source-line {
            color: var(--muted);
            font-size: 13px;
            margin: 4px 0 8px;
        }

        @media (max-width: 900px) {
            .app-hero {
                flex-direction: column;
            }
            .stat-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar(sources: list[dict[str, int | str]]) -> dict[str, object]:
    with st.sidebar:
        st.markdown("### 文档索引")
        _render_upload_panel()
        st.divider()

        st.markdown("### 检索策略")
        search_mode = st.radio(
            "检索模式",
            options=["hybrid", "vector", "keyword"],
            index=0,
            format_func=lambda value: {"hybrid": "混合", "vector": "向量", "keyword": "关键词"}[value],
            horizontal=True,
        )
        top_k = st.slider("最终引用数 Top-K", min_value=1, max_value=10, value=int(os.getenv("TOP_K", "5")))
        candidate_k = st.slider("候选召回数", min_value=top_k, max_value=40, value=max(top_k * 4, 12))
        rewrite_query = st.toggle("查询改写", value=False, help="需要配置 LLM_API_KEY。")

        source_names = ["全部文档"] + [str(item["source"]) for item in sources]
        source_choice = st.selectbox("检索范围", source_names)
        source_filter = None if source_choice == "全部文档" else source_choice

        return {
            "search_mode": search_mode,
            "top_k": top_k,
            "candidate_k": candidate_k,
            "rewrite_query": rewrite_query,
            "source_filter": source_filter,
        }


def _render_upload_panel() -> None:
    uploaded_files = st.file_uploader(
        "上传 PDF / Word / TXT / Markdown",
        type=[extension.lstrip(".") for extension in SUPPORTED_EXTENSIONS],
        accept_multiple_files=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        chunk_size = st.number_input("Chunk 大小", min_value=100, max_value=2000, value=int(os.getenv("CHUNK_SIZE", "500")), step=50)
    with col2:
        chunk_overlap = st.number_input("重叠长度", min_value=0, max_value=500, value=int(os.getenv("CHUNK_OVERLAP", "50")), step=10)

    if st.button("构建索引", type="primary", use_container_width=True):
        if not uploaded_files:
            st.warning("请先选择至少一个文档。")
            return

        with st.spinner("正在解析文档、切分文本并写入向量库..."):
            total_chunks = 0
            reports: list[str] = []
            previews: list[str] = []

            for uploaded_file in uploaded_files:
                report = ingest_bytes(uploaded_file.name, uploaded_file.getvalue(), int(chunk_size), int(chunk_overlap))
                loaded = load_document(UPLOAD_DIR / report["source"])
                chunk_count = report["chunks"]
                total_chunks += chunk_count
                reports.append(f"- {loaded.source_name}: {chunk_count} 个片段")
                previews.append(f"### {loaded.source_name}\n{loaded.text[:800]}")

            st.session_state["last_preview"] = "\n\n".join(previews)
            st.session_state["last_index_report"] = "\n".join(reports)
            st.session_state["last_answer"] = None
            st.success(f"索引构建完成，共写入 {total_chunks} 个文本片段。")
            st.rerun()

    if st.session_state.get("last_index_report"):
        st.markdown(st.session_state["last_index_report"])
    if st.session_state.get("last_preview"):
        with st.expander("最近解析文本预览", expanded=False):
            st.markdown(st.session_state["last_preview"])


def _render_qa_panel(sources: list[dict[str, int | str]], options: dict[str, object]) -> None:
    has_indexed_sources = bool(sources)
    left, right = st.columns([0.5, 0.5], gap="large")

    with left:
        with st.container(border=True):
            st.markdown('<p class="panel-title">问题输入</p>', unsafe_allow_html=True)
            if not has_indexed_sources:
                _render_empty_state("请先在左侧上传文档并构建索引。")

            question = st.text_area(
                "输入你的问题",
                placeholder="例如：这篇论文的核心创新点和实验结论是什么？",
                height=170,
                label_visibility="collapsed",
            )
            submitted = st.button("生成回答", type="primary", disabled=not has_indexed_sources, use_container_width=True)

            if submitted:
                if not question.strip():
                    st.warning("请输入问题。")
                else:
                    with st.spinner("正在检索知识库并生成回答..."):
                        try:
                            result = answer_question(
                                question.strip(),
                                top_k=int(options["top_k"]),
                                search_mode=str(options["search_mode"]),
                                candidate_k=int(options["candidate_k"]),
                                rewrite_query=bool(options["rewrite_query"]),
                                source_filter=options["source_filter"] if options["source_filter"] else None,
                            )
                            st.session_state["last_answer"] = result
                            save_record(
                                question=result.question,
                                answer=result.answer,
                                sources=[citation.__dict__ for citation in result.citations],
                            )
                        except Exception as exc:
                            st.error("操作失败，请检查文件、模型和本地配置；异常详情已隐藏。")

        with st.container(border=True):
            st.markdown('<p class="panel-title">当前检索参数</p>', unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)
            col1.metric("模式", _search_mode_label(str(options["search_mode"])))
            col2.metric("Top-K", int(options["top_k"]))
            col3.metric("候选", int(options["candidate_k"]))
            scope = str(options["source_filter"] or "全部文档")
            st.caption(f"检索范围：{scope}")

    with right:
        with st.container(border=True):
            _render_answer_panel(st.session_state.get("last_answer"))


def _render_answer_panel(result: RagAnswer | None) -> None:
    st.markdown('<p class="panel-title">回答与证据</p>', unsafe_allow_html=True)
    if not result:
        _render_empty_state("提交问题后，这里会展示答案、检索启发式等级和引用依据。")
        return

    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("检索启发式等级", _confidence_label(result.confidence))
    metric2.metric("检索模式", _search_mode_label(result.search_mode))
    metric3.metric("引用数", len(result.citations))

    if result.rewritten_question:
        st.markdown(
            f'<div class="rewrite-box"><strong>检索改写</strong>：{escape(result.rewritten_question)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(result.answer)
    st.divider()
    st.markdown('<p class="panel-title">引用片段</p>', unsafe_allow_html=True)

    if not result.citations:
        _render_empty_state("暂无引用片段。")
        return

    for citation in result.citations:
        location = []
        if citation.page:
            location.append(f"第 {citation.page} 页")
        if citation.section:
            location.append(citation.section)
        location_text = " / ".join(location) if location else "未标注位置"
        title = f"引用{citation.index} | {citation.source}"
        with st.expander(title, expanded=citation.index == 1):
            st.markdown(
                f"""
                <div class="citation-head">
                    <span>{escape(location_text)}</span>
                    <span class="pill">相关度 {citation.score}</span>
                </div>
                <div class="source-line">
                    片段 {citation.chunk_index} · 字符 {citation.char_start}-{citation.char_end} · {escape(citation.retrieval_mode)}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.write(citation.content)


def _render_source_panel(sources: list[dict[str, int | str]]) -> None:
    st.markdown('<p class="panel-title">知识库管理</p>', unsafe_allow_html=True)
    if not sources:
        _render_empty_state("暂无已索引文档。")
        return

    table_col, action_col = st.columns([0.68, 0.32], gap="large")
    with table_col:
        st.dataframe(
            sources,
            hide_index=True,
            use_container_width=True,
            column_config={
                "source": st.column_config.TextColumn("文档"),
                "chunks": st.column_config.NumberColumn("片段数"),
                "pages": st.column_config.NumberColumn("页数"),
                "sections": st.column_config.NumberColumn("章节片段"),
            },
        )
    with action_col:
        with st.container(border=True):
            st.markdown('<p class="panel-title">索引操作</p>', unsafe_allow_html=True)
            source_names = [str(item["source"]) for item in sources]
            selected_source = st.selectbox("选择文档", source_names)
            if st.button("删除索引", use_container_width=True):
                deleted = delete_source(str(selected_source))
                st.success(f"已删除 {selected_source} 的 {deleted} 个文本片段。")
                st.rerun()


def _render_history_panel() -> None:
    st.markdown('<p class="panel-title">历史记录</p>', unsafe_allow_html=True)
    records = list_history(limit=20)

    if not records:
        _render_empty_state("暂无问答记录。")
        return

    for record in records:
        with st.expander(record["question"][:60], expanded=False):
            st.write(record["answer"])
            st.caption(record["create_time"])
            sources = record.get("sources") or []
            if sources:
                st.caption("引用：" + "、".join(str(item.get("source", "未知文档")) for item in sources[:3]))

    if st.button("清空历史记录", use_container_width=True):
        clear_history()
        st.rerun()


def _render_empty_state(message: str) -> None:
    st.markdown(f'<div class="empty-box">{escape(message)}</div>', unsafe_allow_html=True)


def _save_uploaded_file(uploaded_file) -> Path:
    safe_name = _safe_filename(uploaded_file.name)
    saved_path = UPLOAD_DIR / safe_name
    saved_path.write_bytes(uploaded_file.getbuffer())
    return saved_path


def _safe_filename(filename: str) -> str:
    path = Path(filename)
    stem = re.sub(r'[\\/:*?"<>|]+', "_", path.stem).strip() or "uploaded"
    suffix = path.suffix.lower()
    return f"{stem}{suffix}"


def _confidence_label(confidence: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(confidence, confidence)


def _search_mode_label(search_mode: str) -> str:
    return {"hybrid": "混合", "vector": "向量", "keyword": "关键词"}.get(search_mode, search_mode)


if __name__ == "__main__":
    main()
