import pytest
import main
from modules import llm_config_store, settings


def test_empty_knowledge(client):
    assert client.get('/health').status_code == 200
    result = client.post('/ask', json={'question': '问题'}).json()
    assert result['citations'] == []
    assert result['answer_status'] == 'insufficient_evidence'


@pytest.mark.parametrize('payload', [{'question': ' '}, {'question': 'a', 'top_k': 0}, {'question': 'a', 'search_mode': 'bad'}, {'question': 'a', 'top_k': 8, 'candidate_k': 1}])
def test_invalid_ask(client, payload):
    assert client.post('/ask', json=payload).status_code == 422


def test_upload_and_rebuild(client):
    assert client.post('/upload', files={'file': ('a.txt', b'evidence text')}).status_code == 200
    assert client.get('/sources').json()[0]['size'] == 13
    assert client.post('/sources/a.txt/reindex').status_code == 200
    assert client.post('/index/rebuild').status_code == 200
    assert client.delete('/sources/a.txt').json()['deleted'] == 1
    assert client.get('/sources').json()[0]['status'] == 'not_indexed'
    assert client.delete('/documents/a.txt').json()['original_archived'] is True
    assert client.get('/sources').json() == []


@pytest.mark.parametrize('name,content', [('a.exe', b'bad'), ('a.pdf', b'not pdf'), ('a.txt', b''), ('a.txt', b'\x00binary')])
def test_bad_upload(client, name, content):
    assert client.post('/upload', files={'file': (name, content)}).status_code == 400


def test_oversized_upload(client):
    assert client.post('/upload', files={'file': ('a.txt', b'a' * (20 * 1024 * 1024 + 1))}).status_code == 413


def test_secret_errors_and_local_access(client, monkeypatch):
    result = client.post('/llm/configs', json={'name': '', 'api_key': 'secret-key', 'base_url': 'http://bad', 'model': ''})
    assert result.status_code == 422 and 'secret-key' not in result.text
    monkeypatch.setattr(main, 'generate_answer', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('secret-key')))
    assert 'secret-key' not in client.post('/llm/test').text
    assert client.get('/sources', headers={'origin': 'https://evil.example'}).status_code == 403
    assert client.get('/sources', headers={'host': 'evil.example'}).status_code == 403


def test_model_test_does_not_activate(client, monkeypatch):
    first = llm_config_store.save_llm_config('first', 'key111111111', 'https://example.com', 'm')
    second = llm_config_store.save_llm_config('second', 'key222222222', 'https://example.com', 'm')
    monkeypatch.setattr(main, 'generate_answer', lambda *a, **kw: 'ok')
    assert client.post('/llm/test', json={'config_id': second['id']}).status_code == 200
    assert llm_config_store.get_active_llm_config().id == first['id']


def test_conversation_flow(client):
    sid = client.post('/sessions', json={}).json()['id']
    assert client.post('/ask', json={'question': '你好', 'session_id': sid}).status_code == 200
    assert len(client.get(f'/sessions/{sid}/messages').json()) == 1
    assert client.get('/overview').json()['sessions'] == 1
    assert client.patch(f'/sessions/{sid}', json={'title': '标题'}).status_code == 200
    assert client.delete(f'/sessions/{sid}').json()['deleted'] == 1
    assert client.post('/ask', json={'question': '你好', 'session_id': sid}).status_code == 404


def test_config_conflict(client):
    client.post('/upload', files={'file': ('a.txt', b'evidence')})
    config = settings.Settings(embedding_backend='sentence-transformers', embedding_model='missing').model_dump()
    assert client.put('/settings', json=config).status_code == 200
    assert client.post('/ask', json={'question': 'evidence'}).status_code == 409


def test_invalid_split_settings(client):
    payload = settings.Settings().model_dump()
    payload.update(chunk_size=100, chunk_overlap=100)
    assert client.put('/settings', json=payload).status_code == 422
    assert client.get('/settings').json()['chunk_size'] == 500


def test_missing_original_aborts_rebuild(client):
    from modules import vector_store as vs
    from langchain_core.documents import Document
    vs.index_documents([Document(page_content='old original missing', metadata={'source': 'lost.txt'})], 'lost.txt')
    assert client.post('/index/rebuild').status_code == 400
    assert vs._all_documents()[0].page_content == 'old original missing'


def test_original_file_is_restored_on_embedding_error(client, monkeypatch):
    from modules import vector_store as vs, uploads
    client.post('/upload', files={'file': ('a.txt', b'original evidence')})
    monkeypatch.setattr(vs, 'get_embeddings', lambda: (_ for _ in ()).throw(RuntimeError('private-key')))
    response = client.post('/upload', files={'file': ('a.txt', b'new evidence')})
    assert response.status_code == 500 and 'private-key' not in response.text
    assert (uploads.UPLOAD_DIR / 'a.txt').read_bytes() == b'original evidence'
