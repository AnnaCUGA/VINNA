"""Pruebas de memoria: recuerdos, persistencia, historial y comandos (Pruebas 4–7)."""

from __future__ import annotations

import threading

import pytest

from vinna.memory.database import Database
from vinna.memory.long_term import LongTermMemory, MemoryValidationError
from vinna.memory.privacy import looks_sensitive, redact_secrets
from vinna.memory.retrieval import select_relevant
from vinna.memory.short_term import ShortTermMemory


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "m.db")
    yield database
    database.close()


# ---------- recuerdos ----------
def test_remember_and_list(db):  # Prueba 4
    lt = LongTermMemory(db)
    mem, created = lt.remember("Me gusta el té verde", "gustos")
    assert created and mem.id == 1 and mem.category == "gustos" and mem.status == "active"
    assert [m.content for m in lt.list_active()] == ["Me gusta el té verde"]


def test_duplicates_are_detected(db):
    lt = LongTermMemory(db)
    first, _ = lt.remember("Me gusta el té verde")
    again, created = lt.remember("  me gusta el TE verde. ")
    assert created is False and again.id == first.id
    assert lt.count() == 1


def test_persistence_after_reopen(tmp_path):  # Prueba 5
    path = tmp_path / "persist.db"
    db1 = Database(path)
    LongTermMemory(db1).remember("Mi color favorito es el verde")
    ShortTermMemory(db1).save_exchange("hola", "¡hola!", "local")
    db1.close()

    db2 = Database(path)
    try:
        assert [m.content for m in LongTermMemory(db2).list_active()] == ["Mi color favorito es el verde"]
        assert ShortTermMemory(db2).count() == 2
    finally:
        db2.close()


def test_forget_specific_memory(db):  # Prueba 6
    lt = LongTermMemory(db)
    a, _ = lt.remember("dato A")
    b, _ = lt.remember("dato B")
    assert lt.forget(a.id) is True
    assert lt.get(a.id) is None
    assert [m.id for m in lt.list_active()] == [b.id]
    assert lt.forget(999) is False


def test_correct_memory(db):
    lt = LongTermMemory(db)
    m, _ = lt.remember("Vivo en Puebla")
    lt.remember("Tengo un gato")
    assert lt.correct(m.id, "Vivo en Oaxaca").content == "Vivo en Oaxaca"
    with pytest.raises(MemoryValidationError, match="Ya existe"):
        lt.correct(m.id, "tengo un gato")


@pytest.mark.parametrize("text", [
    "mi contraseña es 1234", "mi password es abc", "la api key es xyz",
    "sk-abcdefghijklmnopqrstuvwx", "tarjeta 4111 1111 1111 1111",
])
def test_sensitive_data_is_rejected(db, text):
    with pytest.raises(MemoryValidationError):
        LongTermMemory(db).remember(text)
    assert looks_sensitive(text)


def test_validation(db):
    lt = LongTermMemory(db)
    with pytest.raises(MemoryValidationError):
        lt.remember("   ")
    with pytest.raises(MemoryValidationError):
        lt.remember("x" * 600)
    with pytest.raises(MemoryValidationError):
        lt.remember("ok", category="categoría con espacios")


def test_temporary_memories_expire(db):
    lt = LongTermMemory(db, temporary_hours=-1)  # ya caducado al crearse
    m, _ = lt.remember("reunión hoy", temporary=True)
    assert m.kind == "temporary"
    assert lt.list_active() == []
    assert lt.get(m.id).status == "expired"


def test_clear_memories_is_verifiable(db):
    lt = LongTermMemory(db)
    for i in range(3):
        lt.remember(f"dato {i}")
    assert lt.clear() == 3
    assert lt.count(active_only=False) == 0


# ---------- historial ----------
def test_history_window_is_bounded(db):
    st = ShortTermMemory(db, max_messages=4, max_chars=10_000)
    for i in range(10):
        st.save_exchange(f"pregunta {i}", f"respuesta {i}", "local")
    recent = st.recent()
    assert len(recent) == 4
    assert recent[0].role == "user" and recent[-1].content == "respuesta 9"


def test_history_char_budget(db):
    st = ShortTermMemory(db, max_messages=50, max_chars=500)
    for i in range(10):
        st.save_exchange("a" * 100, "b" * 100, "local")
    total = sum(len(m.content) for m in st.recent())
    assert total <= 500


def test_secrets_are_redacted_in_history(db):
    st = ShortTermMemory(db)
    st.save_exchange("mi clave es sk-abcdefghijklmnopqrstuvwx", "ok", "local")
    assert "sk-abc" not in st.recent()[0].content
    assert "[dato oculto]" in redact_secrets("sk-abcdefghijklmnopqrstuvwx")


# ---------- concurrencia ----------
def test_concurrent_writes_are_safe(db):
    lt = LongTermMemory(db)
    st = ShortTermMemory(db)
    errors = []

    def writer(n):
        try:
            for i in range(20):
                lt.remember(f"hilo {n} dato {i}")
                st.save_exchange(f"q{n}-{i}", f"a{n}-{i}", "local")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert lt.count() == 80 and st.count() == 160


# ---------- recuperación ----------
def test_retrieval_prioritizes_keywords(db):
    lt = LongTermMemory(db)
    for i in range(10):
        lt.remember(f"dato irrelevante número {i}")
    lt.remember("Mi perro se llama Toby", "mascotas")
    picked = select_relevant(lt.list_active(), "¿Cómo se llama mi perro?", limit=3)
    assert any("Toby" in m.content for m in picked)
    assert len(picked) == 3
