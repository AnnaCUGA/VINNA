"""Respuestas sobre la propia memoria, sin pasar por el modelo.

Los modelos pequeños tienden a contestar "no tengo acceso a tu información"
ante preguntas abiertas como "¿qué recuerdas de mí?", aunque los datos estén
en el prompt. Estas preguntas se responden aquí directamente desde la base
de datos, así la respuesta es siempre exacta.
"""

from __future__ import annotations

import re

from vinna.memory.long_term import Memory, normalize
from vinna.memory.pronouns import to_second_person

# Se compara contra el texto normalizado (minúsculas y sin acentos).
_RECALL_PATTERNS = [
    re.compile(r"\bque (recuerdas|sabes|te acuerdas|tienes guardado|has guardado|conoces) (de|sobre|acerca de) mi\b"),
    re.compile(r"\bque (te he contado|te conte|te dije que recordaras|me has guardado)\b"),
    re.compile(r"\b(cuales|que) son (mis|tus) recuerdos\b"),
    re.compile(r"\bque recuerdos tienes\b"),
    re.compile(r"\bque recuerdas\s*$"),
    re.compile(r"\b(cuentame|dime|hablame) (algo |que sabes |lo que sabes )?(sobre|de|acerca de) mi\b"),
    re.compile(r"\bquien soy( yo)?$"),
]


def is_recall_question(text: str) -> bool:
    """True si el usuario pregunta en general qué sabe/recuerda VINNA de él o ella."""
    clean = normalize(text).strip(" ¿?¡!.")
    return any(p.search(clean) for p in _RECALL_PATTERNS)


def format_recall(memories: list[Memory]) -> str:
    if not memories:
        return (
            "Todavía no tengo nada guardado sobre ti. Si quieres que recuerde algo, "
            "escríbelo así:  !recuerda Me gusta el té verde"
        )
    if len(memories) == 1:
        return f"Esto es lo que recuerdo de ti: {to_second_person(memories[0].content)}."
    items = "\n".join(f"- {to_second_person(m.content)}" for m in memories)
    return f"Esto es lo que recuerdo de ti:\n{items}"
