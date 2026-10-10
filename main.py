from __future__ import annotations

from dataclasses import asdict
import ipaddress
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / '.env')

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator, model_validator

from modules import conversations
from modules.document_loader import load_document
from modules.history import clear_history, list_history, save_record, count_history
from modules.llm_config_store import activate_llm_config, delete_llm_config, list_llm_configs, save_llm_config, get_llm_config as find_config
from modules.llm_client import generate_answer, get_llm_config
from modules.rag_chain import answer_question
from modules.settings import STATE_LOCK, Settings, get_settings, save_settings
from modules.text_splitter import split_text
from modules.uploads import UPLOAD_DIR, MAX_UPLOAD_BYTES, ingest_bytes, reindex_source, safe_filename, archive_document
from modules.vector_store import IndexCompatibilityError, delete_source, list_indexed_sources, index_status, rebuild_index

app = FastAPI(title='RAG Studio', version='2.0.0')
ORIGINS = {f'http://{host}:{port}' for host in ('localhost', '127.0.0.1') for port in (5173, 4173, 8000)}
app.add_middleware(CORSMiddleware, allow_origins=sorted(ORIGINS), allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], allow_headers=['Content-Type'])


@app.middleware('http')
async def local_only(request: Request, call_next):
    peer = request.client.host if request.client else ''
    try:
        local = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        local = peer == 'testclient'
    if not local or request.url.hostname not in {'127.0.0.1', 'localhost', '::1', 'testserver'}:
        return JSONResponse({'detail': '仅允许本机访问'}, status_code=403)
    origin = request.headers.get('origin')
    if origin and origin not in ORIGINS:
        return JSONResponse({'detail': '不允许此来源访问本地服务'}, status_code=403)
    length = request.headers.get('content-length')
    if length:
        try:
            if int(length) < 0 or int(length) > MAX_UPLOAD_BYTES + 1024 * 1024:
                return JSONResponse({'detail': '请求体超过大小限制'}, status_code=413)
        except ValueError:
            return JSONResponse({'detail': '无效 Content-Length'}, status_code=400)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic's default errors include input values, possibly including API keys.
    return JSONResponse({'detail': '参数无效，请检查字段类型、范围和必填项',
                         'fields': ['.'.join(map(str, error['loc'])) for error in exc.errors()]}, status_code=422)


@app.exception_handler(IndexCompatibilityError)
async def incompatible(request, exc):
    return JSONResponse({'detail': '索引模型不兼容，请全库重建；旧索引仍保留，BM25 可用'}, status_code=409)


@app.exception_handler(Exception)
async def internal_error(request, exc):
    return JSONResponse({'detail': '操作失败，原始异常已隐藏。请检查文件格式、模型是否已在本地安装及配置是否有效'}, status_code=500)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(4, ge=1, le=20)
    search_mode: Literal['hybrid', 'vector', 'keyword'] = 'hybrid'
    candidate_k: int | None = Field(None, ge=1, le=100)
    rewrite_query: bool = False
    source_filter: str | None = Field(None, max_length=180)
    session_id: str | None = Field(None, max_length=64)
    reranker: Literal['none', 'lightweight', 'semantic'] | None = None

    @model_validator(mode='after')
    def ranges(self):
        if not self.question.strip() or (self.candidate_k is not None and self.candidate_k < self.top_k):
            raise ValueError('问题不能为空，候选数必须不小于 Top-K')
        return self


class LlmConfigRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    api_key: str = Field(min_length=1, max_length=1000)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    active: bool = False

    @field_validator('name', 'api_key', 'model', 'base_url')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('不能为空')
        return value.strip()

    @field_validator('base_url')
    @classmethod
    def url(cls, value):
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('地址不得含凭据、查询参数或片段')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}):
            raise ValueError('远程模型必须使用 HTTPS')
        return value


class LlmTestRequest(BaseModel):
    config_id: str | None = Field(None, max_length=64)


class SessionRequest(BaseModel):
    title: str = Field('新会话', min_length=1, max_length=100)

    @field_validator('title')
    @classmethod
    def title_nonempty(cls, value):
        if not value.strip():
            raise ValueError('标题不能为空')
        return value.strip()


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/')
def root():
    return {'name': 'RAG Studio V2.0', 'docs': 'http://127.0.0.1:8000/docs', 'frontend': 'http://127.0.0.1:5173/'}


@app.get('/sources')
def sources():
    with STATE_LOCK:
        indexed = {item['source']: item for item in list_indexed_sources()}
        files = {p.name: p for p in UPLOAD_DIR.glob('*') if p.is_file() and not p.name.startswith('.')}
        result = []
        for name in sorted(set(indexed) | set(files)):
            item = dict(indexed.get(name, {'source': name, 'chunks': 0, 'pages': 0, 'sections': 0}))
            item.update(type=Path(name).suffix.lower(), size=files[name].stat().st_size if name in files else None,
                        status='indexed' if name in indexed else 'not_indexed', original_available=name in files)
            result.append(item)
        return result


@app.delete('/sources/{source_name}')
def delete_source_api(source_name: str):
    # Compatibility: this endpoint deletes only the index, retaining the original.
    return {'source': source_name, 'deleted': delete_source(source_name)}


@app.post('/sources/{source_name}/reindex')
def reindex_api(source_name: str):
    try:
        return reindex_source(source_name)
    except FileNotFoundError:
        raise HTTPException(404, '原文件不存在，请重新上传')
    except IndexCompatibilityError:
        raise
    except ValueError:
        raise HTTPException(400, '文件或切分参数无效，旧索引已保留')


@app.delete('/documents/{source_name}')
def archive_document_api(source_name: str):
    try:
        return archive_document(source_name)
    except ValueError:
        raise HTTPException(400, '无效的文件名')


@app.post('/index/rebuild')
def rebuild_api():
    with STATE_LOCK:
        names = {item['source'] for item in list_indexed_sources()}
        names.update(p.name for p in UPLOAD_DIR.glob('*') if p.is_file() and not p.name.startswith('.'))
        config = get_settings()
        docs = []
        for name in sorted(names):
            try:
                path = UPLOAD_DIR / safe_filename(name)
                loaded = load_document(path)
                docs.extend(split_text(loaded.text, name, config.chunk_size, config.chunk_overlap))
            except Exception:
                raise HTTPException(400, '存在缺失或无法解析的原文件，已停止重建，旧索引保留')
        return {'chunks': rebuild_index(docs), 'documents': len(names)}


@app.post('/upload')
async def upload(file: UploadFile = File(...)):
    try:
        name = safe_filename(file.filename or '')
        content = bytearray()
        while block := await file.read(1024 * 1024):
            content.extend(block)
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, '文件不得超过 20 MiB')
        return await run_in_threadpool(ingest_bytes, name, bytes(content))
    except IndexCompatibilityError:
        raise
    except ValueError:
        raise HTTPException(400, '文件无效：请检查名称、类型、内容或大小（上限 20 MiB）')
    finally:
        await file.close()


@app.post('/ask')
def ask(payload: AskRequest):
    # Serialize turns in this single-user process to keep history ordered.
    with STATE_LOCK:
        try:
            history = conversations.history_messages(payload.session_id) if payload.session_id else []
        except KeyError:
            raise HTTPException(404, '会话不存在')
        result = answer_question(payload.question.strip(), top_k=payload.top_k, search_mode=payload.search_mode,
            candidate_k=payload.candidate_k, rewrite_query=payload.rewrite_query,
            source_filter=payload.source_filter, history=history, reranker=payload.reranker)
        response = asdict(result)
        if payload.session_id:
            conversations.save_turn(payload.session_id, result.question, response)
        else:
            save_record(result.question, result.answer, response['citations'])
        return {**response, 'session_id': payload.session_id}


@app.get('/sessions')
def sessions():
    return conversations.list_sessions()


@app.post('/sessions')
def create_session(payload: SessionRequest | None = None):
    return conversations.create_session(payload.title if payload else '新会话')


@app.get('/sessions/{session_id}/messages')
def messages(session_id: str):
    try:
        return conversations.get_turns(session_id)
    except KeyError:
        raise HTTPException(404, '会话不存在')


@app.patch('/sessions/{session_id}')
def rename_session(session_id: str, payload: SessionRequest):
    if not conversations.rename_session(session_id, payload.title):
        raise HTTPException(404, '会话不存在')
    return {'id': session_id, 'title': payload.title}


@app.delete('/sessions/{session_id}')
def delete_session(session_id: str):
    with STATE_LOCK:
        return {'deleted': conversations.delete_session(session_id)}


@app.get('/history')
def history(limit: int = Query(20, ge=1, le=200)):
    return list_history(limit)


@app.delete('/history')
def clear_history_api():
    clear_history()
    return {'status': 'ok'}


@app.get('/overview')
def overview():
    items = sources()
    return {**conversations.statistics(), 'documents': len(items),
            'chunks': sum(item['chunks'] for item in items), 'model': get_llm_config(),
            'index': index_status(), 'legacy_history_count': count_history()}


@app.get('/settings')
def settings():
    return {**get_settings().model_dump(), 'index': index_status(), 'max_upload_bytes': MAX_UPLOAD_BYTES}


@app.put('/settings')
def update_settings(payload: Settings):
    save_settings(payload)
    return settings()


@app.get('/llm/status')
def llm_status():
    return get_llm_config()


@app.get('/llm/configs')
def llm_configs():
    return list_llm_configs(mask_keys=True)


@app.post('/llm/configs')
def create_llm_config(payload: LlmConfigRequest):
    with STATE_LOCK:
        return save_llm_config(**payload.model_dump())


@app.post('/llm/configs/{config_id}/activate')
def activate_llm_config_api(config_id: str):
    with STATE_LOCK:
        try:
            return activate_llm_config(config_id)
        except ValueError:
            raise HTTPException(404, '模型配置不存在')


@app.delete('/llm/configs/{config_id}')
def delete_llm_config_api(config_id: str):
    with STATE_LOCK:
        return {'id': config_id, 'deleted': delete_llm_config(config_id)}


@app.post('/llm/test')
def llm_test(payload: LlmTestRequest | None = None):
    config_id = payload.config_id if payload else None
    if config_id and not find_config(config_id):
        raise HTTPException(404, '模型配置不存在')
    try:
        answer = generate_answer([{'role': 'user', 'content': '只回复：连接成功'}], temperature=0, config_id=config_id)
        if not answer.strip():
            raise RuntimeError('empty')
        return {'status': 'ok', 'message': '连接成功'}
    except Exception:
        raise HTTPException(502, '模型连接失败，请检查 API 配置、网络或额度')


# V1 private helper retained for imports.
_safe_filename = safe_filename
