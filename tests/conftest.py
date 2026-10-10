import os
import tempfile

# Set BEFORE importing application modules; never open the user's database/index.
os.environ['RAG_DATA_DIR'] = tempfile.mkdtemp(prefix='rag-studio-tests-')
os.environ['LLM_API_KEY'] = ''
os.environ['DEEPSEEK_API_KEY'] = ''
os.environ['EMBEDDING_BACKEND'] = 'hash'

import pytest
from fastapi.testclient import TestClient
import main
from modules import settings, vector_store, uploads, history, conversations, llm_config_store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'SETTINGS_PATH', tmp_path / 'settings.json')
    monkeypatch.setattr(vector_store, 'DEFAULT_VECTOR_DIR', tmp_path / 'vectors')
    monkeypatch.setattr(vector_store, 'MANIFEST_PATH', tmp_path / 'vectors' / 'active.json')
    monkeypatch.setattr(uploads, 'UPLOAD_DIR', tmp_path / 'uploads')
    monkeypatch.setattr(uploads, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path / 'uploads')
    monkeypatch.setattr(history, 'DB_PATH', tmp_path / 'history.sqlite3')
    monkeypatch.setattr(conversations, 'DB_PATH', tmp_path / 'sessions.sqlite3')
    monkeypatch.setattr(llm_config_store, 'CONFIG_PATH', tmp_path / 'configs.json')
    settings.save_settings(settings.Settings())


@pytest.fixture
def client():
    with TestClient(main.app, raise_server_exceptions=False) as value:
        yield value
