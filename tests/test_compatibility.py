import json
import sqlite3
from modules import history, llm_config_store, vector_store as vs, settings
from langchain_core.documents import Document


def test_legacy_history_still_readable(client):
    history.init_db()
    with sqlite3.connect(history.DB_PATH) as db:
        db.execute('INSERT INTO qa_history(question,answer,sources) VALUES (?,?,?)', ('old question', 'old answer', '[]'))
    assert client.get('/history').json()[0]['question'] == 'old question'
    assert client.get('/sessions').json() == []


def test_legacy_index_survives_first_snapshot():
    old = vs.get_vector_store(collection_name='rag_documents')
    old.add_documents([Document(page_content='legacy data', metadata={'source': 'old.txt', 'chunk_index': 0})], ids=['old.txt:0'])
    vs.index_documents([Document(page_content='new data', metadata={'source': 'new.txt', 'chunk_index': 0})], 'new.txt')
    assert {doc.metadata['source'] for doc in vs._all_documents()} == {'old.txt', 'new.txt'}
    assert old.get()['ids'] == ['old.txt:0']


def test_corrupt_model_file_not_overwritten():
    llm_config_store.CONFIG_PATH.write_text('{broken', encoding='utf-8')
    import pytest
    with pytest.raises(ValueError):
        llm_config_store.save_llm_config('a', 'secret', 'https://example.com', 'model')
    assert llm_config_store.CONFIG_PATH.read_text() == '{broken'
