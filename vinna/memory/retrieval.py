"""Selección de recuerdos relevantes para incluir en el prompt.

Fase 1: búsqueda por palabras clave (sin embeddings ni ChromaDB, para mantener
bajo el consumo de recursos). Si hay pocos recuerdos se incluyen todos; si hay
muchos se priorizan los que comparten palabras con el mensaje y luego los más
recientes. En la Fase 2 este módulo podrá sustituirse por búsqueda semántica
sin cambiar el resto del sistema.
"""

from __future__ import annotations

import re

from vinna.memory.long_term import Memory, normalize

STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "y", "o",
    "que", "en", "es", "mi", "mis", "tu", "tus", "me", "te", "se", "lo", "le", "por", "para",
    "con", "sin", "como", "mas", "muy", "ya", "su", "sus", "yo", "si", "no", "eso", "esto",
    "cual", "cuales", "quien", "donde", "cuando", "hay", "son", "soy", "eres", "fue", "ser",
}


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9ñ]+", normalize(text))
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def select_relevant(memories: list[Memory], query: str, limit: int) -> list[Memory]:
    if limit <= 0 or not memories:
        return []
    if len(memories) <= limit:
        return memories
    query_words = _keywords(query)

    def score(m: Memory) -> tuple[int, int]:
        overlap = len(query_words & (_keywords(m.content) | {m.category}))
        return (overlap, m.id)  # empate -> el más reciente

    ranked = sorted(memories, key=score, reverse=True)[:limit]
    return sorted(ranked, key=lambda m: m.id)
