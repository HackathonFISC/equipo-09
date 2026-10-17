"""Dónde guarda el grafo sus checkpoints (pausas HITL) según la configuración."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from puente_api.config import Settings
from puente_api.graph import checkpoint


@pytest.fixture
def use_settings(monkeypatch):
    def apply(**kw):
        monkeypatch.setattr(checkpoint, "get_settings", lambda: Settings(_env_file=None, **kw))
        checkpoint.get_checkpointer.cache_clear()
        return checkpoint.get_checkpointer()

    yield apply
    checkpoint.get_checkpointer.cache_clear()


def test_postgres_without_checkpoint_path_uses_memory(use_settings):
    saver = use_settings(database_url="postgresql+psycopg://u:p@db/puente")
    assert isinstance(saver, InMemorySaver)


def test_checkpoint_path_persists_even_with_postgres(use_settings, tmp_path):
    path = tmp_path / "data" / "checkpoints.sqlite"
    saver = use_settings(
        database_url="postgresql+psycopg://u:p@db/puente", checkpoint_path=str(path)
    )
    assert isinstance(saver, SqliteSaver)
    assert path.exists()  # crea la carpeta del volumen si falta
    saver.conn.close()


def test_sqlite_file_gets_a_sibling_checkpoint_file(use_settings, tmp_path):
    saver = use_settings(database_url=f"sqlite:///{tmp_path / 'puente.db'}")
    assert isinstance(saver, SqliteSaver)
    assert (tmp_path / "puente-checkpoints.sqlite").exists()
    saver.conn.close()
