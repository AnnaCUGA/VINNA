"""Pruebas del orquestador y los comandos (conversación, contexto, errores)."""

from __future__ import annotations

from vinna.brain.model_router import Mode
from vinna.core.events import ReplyKind
from tests.conftest import FakeProvider


def test_conversation_is_saved_once(build):  # Prueba 2 (con modelo simulado)
    orch, local, _ = build()
    reply = orch.handle("Hola VINNA")
    assert reply.kind is ReplyKind.ASSISTANT and reply.text == "hola desde local" and reply.provider == "local"
    history = orch.short_term.recent()
    assert [(m.role, m.content) for m in history] == [("user", "Hola VINNA"), ("assistant", "hola desde local")]


def test_messages_contain_personality_memories_and_history(build):
    orch, local, _ = build()
    orch.handle("!recuerda #gustos Me gusta el té verde")
    orch.handle("primer mensaje")
    orch.handle("segundo mensaje")
    sent = local.calls[-1]
    assert sent[0]["role"] == "system"
    assert "Eres VINNA" in sent[0]["content"] and "Me gusta el té verde" in sent[0]["content"]
    assert [m["content"] for m in sent[1:]] == ["primer mensaje", "hola desde local", "segundo mensaje"]
    # sin duplicar el mensaje actual
    assert sum(1 for m in sent if m["content"] == "segundo mensaje") == 1


def test_commands_are_not_saved_in_history(build):
    orch, local, _ = build()
    orch.handle("!recuerda algo importante")
    orch.handle("!recuerdos")
    orch.handle("!ayuda")
    assert orch.short_term.count() == 0
    assert local.calls == []  # los comandos no llegan al modelo


def test_clear_history_does_not_keep_the_command(build):  # Prueba 7
    orch, _, _ = build()
    orch.handle("hola")
    orch.handle("¿qué tal?")
    reply = orch.handle("!borrar-historial")
    assert "Quedan 0" in reply.text
    assert orch.short_term.count() == 0


def test_remember_forget_through_commands(build):  # Pruebas 4 y 6
    orch, _, _ = build()
    assert "#1" in orch.handle("!recuerda Mi robot se llama VINNA").text
    assert "Mi robot se llama VINNA" in orch.handle("!recuerdos").text
    assert "eliminado" in orch.handle("!olvida 1").text
    assert "Todavía no tengo recuerdos" in orch.handle("!recuerdos").text
    assert orch.handle("!olvida 1").kind is ReplyKind.ERROR


def test_clear_memories_requires_confirmation(build):
    orch, _, _ = build()
    orch.handle("!recuerda uno")
    orch.handle("!recuerda dos")
    assert "confirmar" in orch.handle("!borrar-recuerdos").text
    assert orch.long_term.count() == 2
    assert "Quedan 0" in orch.handle("!borrar-recuerdos confirmar").text
    assert orch.long_term.count() == 0


def test_unknown_command(build):
    orch, _, _ = build()
    reply = orch.handle("!volar")
    assert reply.kind is ReplyKind.ERROR and "!ayuda" in reply.text


def test_model_error_is_reported_and_not_saved(build):  # Prueba 12
    orch, _, _ = build(local=FakeProvider("local", fail="No se pudo conectar con Ollama"))
    reply = orch.handle("hola")
    assert reply.kind is ReplyKind.ERROR and "Ollama" in reply.text
    assert orch.short_term.count() == 0  # no queda un mensaje huérfano


def test_unexpected_exception_does_not_crash(build):
    class Broken(FakeProvider):
        def chat(self, messages):
            raise RuntimeError("boom")

    orch, _, _ = build(local=Broken("local"))
    reply = orch.handle("hola")
    assert reply.kind is ReplyKind.ERROR


def test_memories_not_sent_to_cloud_by_default(build):
    orch, _, cloud = build(mode=Mode.CLOUD)
    orch.handle("!recuerda Mi secreto favorito es el chocolate")
    orch.handle("hola")
    assert "chocolate" not in cloud.calls[-1][0]["content"]


def test_memories_sent_to_cloud_when_allowed(build):
    orch, _, cloud = build(mode=Mode.CLOUD, privacy__send_memories_to_cloud=True)
    orch.handle("!recuerda Me gusta el chocolate")
    orch.handle("hola")
    assert "chocolate" in cloud.calls[-1][0]["content"]


def test_mode_command_switches_provider(build):
    orch, local, cloud = build()
    orch.handle("!modo nube")
    reply = orch.handle("hola")
    assert reply.provider == "cloud" and len(cloud.calls) == 1 and local.calls == []


def test_hybrid_fallback_notice_reaches_user(build):  # Prueba 10
    orch, _, _ = build(cloud=FakeProvider("cloud", fail="sin red"), mode=Mode.HYBRID, ai__hybrid__prefer="cloud")
    orch.router.hybrid_prefer = "cloud"
    reply = orch.handle("hola")
    assert reply.provider == "local" and reply.notice


def test_empty_input_is_ignored(build):
    orch, local, _ = build()
    assert orch.handle("   ") is None
    assert local.calls == []
