"""Pruebas de la personalidad (Prueba 3)."""

from __future__ import annotations

from pathlib import Path

from vinna.memory.long_term import Memory
from vinna.personality.character import Personality

PROJECT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "personality.yaml"


def _memory(text: str, mid: int = 1) -> Memory:
    return Memory(mid, text, "gustos", "permanent", "active", "2026-01-01T00:00:00+00:00",
                  "2026-01-01T00:00:00+00:00", None)


def test_project_personality_file_loads():
    p = Personality.load(PROJECT_CONFIG)
    assert p.name == "VINNA"
    assert "curiosa" in p.traits
    prompt = p.build_system_prompt()
    assert "Eres VINNA" in prompt
    assert "español" in prompt
    assert "conciencia" in prompt  # regla: no afirmar conciencia


def test_missing_file_uses_defaults(tmp_path):
    p = Personality.load(tmp_path / "no-existe.yaml")
    assert p.name == "VINNA"


def test_custom_personality(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("name: Robi\nresponse_length: breve\ntraits: [serio]\ncampo_desconocido: 1\n", encoding="utf-8")
    p = Personality.load(f)
    prompt = p.build_system_prompt()
    assert "Eres Robi" in prompt and "serio" in prompt and "breve" in prompt


def test_memories_are_listed_and_absence_is_explicit():
    p = Personality()
    with_mem = p.build_system_prompt([_memory("Le gusta el té verde")])
    assert "Le gusta el té verde" in with_mem
    assert "LO QUE SABES DEL USUARIO" in with_mem  # presentado como datos directos
    assert "No digas que no tienes memoria" in with_mem
    assert "segunda persona" in with_mem  # los datos son del usuario, no de VINNA
    first_person = p.build_system_prompt([_memory("Me gusta el café")])
    assert "Te gusta el café" in first_person  # se pasa al modelo en segunda persona
    without = p.build_system_prompt([])
    assert "no lo recuerdas" in without  # evita inventar recuerdos
