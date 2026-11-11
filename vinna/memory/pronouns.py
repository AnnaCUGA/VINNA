"""Convierte recuerdos en primera persona a segunda persona.

Los recuerdos se guardan como los escribe el usuario ("Me gusta el té verde").
Si se le pasan así al modelo, los modelos pequeños los repiten como propios
("Me gusta tomar té verde"). Antes de enviarlos se convierten a segunda
persona ("Te gusta el té verde") con reglas sencillas para los casos comunes;
si ninguna regla aplica, el texto se deja igual.
"""

from __future__ import annotations

import re

# Reglas al inicio de la frase (orden importa: las más largas primero).
_START_RULES = [
    ("no me gusta", "no te gusta"), ("no me gustan", "no te gustan"),
    ("me gustan", "te gustan"), ("me gusta", "te gusta"), ("me encantan", "te encantan"),
    ("me encanta", "te encanta"), ("me llamo", "te llamas"), ("me dicen", "te dicen"),
    ("me interesa", "te interesa"), ("me interesan", "te interesan"),
    ("estoy", "estás"), ("soy", "eres"), ("tengo", "tienes"), ("vivo", "vives"),
    ("trabajo", "trabajas"), ("estudio", "estudias"), ("odio", "odias"), ("prefiero", "prefieres"),
    ("quiero", "quieres"), ("necesito", "necesitas"), ("hablo", "hablas"), ("juego", "juegas"),
    ("mis", "tus"), ("mi", "tu"), ("yo", "tú"),
]
# Posesivos dentro de la frase ("el nombre de mi gato" → "el nombre de tu gato").
_INNER_RULES = [(r"\bmis\b", "tus"), (r"\bmi\b", "tu"), (r"\bconmigo\b", "contigo")]


def _match_case(original: str, replacement: str) -> str:
    return replacement[0].upper() + replacement[1:] if original[:1].isupper() else replacement


def to_second_person(text: str) -> str:
    stripped = text.strip()
    lower = stripped.lower()
    for first, second in _START_RULES:
        if lower == first or lower.startswith(first + " "):
            stripped = _match_case(stripped, second) + stripped[len(first):]
            break
    head, rest = stripped[:1], stripped[1:]
    for pattern, repl in _INNER_RULES:
        rest = re.sub(pattern, repl, rest)
    return head + rest
