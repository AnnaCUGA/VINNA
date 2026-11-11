"""Pruebas del cerebro: cliente Ollama, cliente OpenAI y enrutador de modelos."""

from __future__ import annotations

import socket

import pytest

from vinna.brain.base import ProviderError
from vinna.brain.cloud_model import OpenAIClient
from vinna.brain.local_model import OllamaClient
from vinna.brain.model_router import Mode, ModelRouter, RouterError
from tests.conftest import FakeProvider


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------- Ollama (Prueba 2 y 8, con servidor simulado) ----------
def test_ollama_chat_over_http(fake_ollama):
    host, handler = fake_ollama
    client = OllamaClient(host, "qwen2.5:0.5b", timeout=5)
    answer = client.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "hola"}])
    assert answer == "eco: hola"
    sent = handler.received[-1]
    assert sent["stream"] is False and sent["model"] == "qwen2.5:0.5b"
    assert sent["messages"][0]["role"] == "system"


def test_ollama_check_detects_model(fake_ollama):
    host, _ = fake_ollama
    assert OllamaClient(host, "qwen2.5:0.5b").check()[0] is True
    ok, detail = OllamaClient(host, "llama3").check()
    assert ok is False and "ollama pull llama3" in detail


def test_ollama_missing_model_message(fake_ollama):
    host, _ = fake_ollama
    with pytest.raises(ProviderError, match="ollama pull otro"):
        OllamaClient(host, "otro", timeout=5).chat([{"role": "user", "content": "x"}])


def test_ollama_not_running_gives_clear_error():
    # En Windows rechazar una conexión a un puerto cerrado tarda ~2 s; el timeout debe ser mayor.
    client = OllamaClient(f"http://127.0.0.1:{_free_port()}", "qwen2.5:0.5b", timeout=10)
    with pytest.raises(ProviderError, match="No se pudo conectar con Ollama"):
        client.chat([{"role": "user", "content": "hola"}])
    assert client.check()[0] is False


# ---------- OpenAI (Prueba 9: sin clave debe fallar de forma clara) ----------
def test_openai_without_key_is_not_configured():
    client = OpenAIClient(None, "gpt-4o-mini")
    assert client.is_configured() is False
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        client.chat([{"role": "user", "content": "hola"}])


def test_openai_client_uses_sdk(monkeypatch):
    """Simula el SDK de OpenAI para comprobar la llamada sin usar Internet."""
    import sys
    import types

    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            msg = types.SimpleNamespace(content=" hola nube ")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["init"] = kwargs
            self.chat = types.SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    client = OpenAIClient("sk-test", "gpt-test")
    assert client.chat([{"role": "user", "content": "hola"}]) == "hola nube"
    assert captured["model"] == "gpt-test" and "temperature" not in captured


# ---------- Enrutador ----------
def _build(**kw):
    return lambda text: [{"role": "user", "content": text}]


def test_local_mode_never_uses_cloud():
    local, cloud = FakeProvider("local", fail="caído"), FakeProvider("cloud")
    router = ModelRouter(local, cloud, Mode.LOCAL)
    with pytest.raises(RouterError, match="caído"):
        router.generate("hola", _build())
    assert cloud.calls == []  # no cambia de proveedor en silencio


def test_cloud_mode_never_uses_local():
    local, cloud = FakeProvider("local"), FakeProvider("cloud", fail="sin red")
    router = ModelRouter(local, cloud, Mode.CLOUD)
    with pytest.raises(RouterError, match="sin red"):
        router.generate("hola", _build())
    assert local.calls == []


def test_hybrid_falls_back_to_local_with_notice():  # Prueba 10
    local, cloud = FakeProvider("local", "respaldo"), FakeProvider("cloud", fail="sin red")
    router = ModelRouter(local, cloud, Mode.HYBRID, hybrid_prefer="cloud")
    result = router.generate("hola", _build())
    assert result.text == "respaldo" and result.provider == "local"
    assert result.fallback_notice and "respaldo" in result.fallback_notice


def test_hybrid_both_fail_reports_both():
    router = ModelRouter(FakeProvider("local", fail="A"), FakeProvider("cloud", fail="B"), Mode.HYBRID)
    with pytest.raises(RouterError) as exc:
        router.generate("hola", _build())
    assert "A" in str(exc.value) and "B" in str(exc.value)


def test_hybrid_complex_tasks_go_to_cloud_first():
    local, cloud = FakeProvider("local"), FakeProvider("cloud")
    router = ModelRouter(local, cloud, Mode.HYBRID, hybrid_prefer="local", complex_tasks_to_cloud=True)
    assert router.plan("hola") == ["local", "cloud"]
    assert router.plan("Analiza este texto por favor") == ["cloud", "local"]


def test_hybrid_skips_unconfigured_cloud():
    router = ModelRouter(FakeProvider("local"), FakeProvider("cloud", configured=False), Mode.HYBRID,
                         hybrid_prefer="cloud")
    assert router.plan("hola") == ["local"]


def test_mode_parsing():
    assert Mode.parse("nube") is Mode.CLOUD
    assert Mode.parse("híbrido") is Mode.HYBRID
    assert Mode.parse("LOCAL") is Mode.LOCAL
    with pytest.raises(ValueError):
        Mode.parse("marte")
