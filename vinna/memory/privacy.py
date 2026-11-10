"""Reglas de privacidad para la memoria.

VINNA no debe guardar contraseñas, claves API ni otros datos sensibles. Estas
comprobaciones son heurísticas (expresiones regulares): no son perfectas, pero
evitan los casos más comunes. No dependen del modelo de lenguaje.
"""

from __future__ import annotations

import re

# Patrones que parecen secretos concretos (se ocultan en el historial).
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),            # claves estilo OpenAI
    re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{20,}"),  # tokens GitHub
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                 # AWS
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),           # Google API
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),               # posibles tarjetas/cuentas
]

# Palabras que indican que el usuario intenta guardar algo sensible.
SENSITIVE_WORDS = re.compile(
    r"\b(contrase(?:ñ|n)a|password|passwd|clave\s+api|api\s*key|token|pin|nip|cvv|"
    r"clabe|curp|rfc|n[uú]mero\s+de\s+tarjeta|tarjeta\s+de\s+cr[eé]dito)\b",
    re.IGNORECASE,
)


def looks_sensitive(text: str) -> bool:
    """True si el texto parece contener un secreto o dato sensible."""
    if SENSITIVE_WORDS.search(text):
        return True
    return any(p.search(text) for p in SECRET_PATTERNS)


def redact_secrets(text: str) -> str:
    """Sustituye secretos concretos por un marcador antes de guardar texto."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[dato oculto]", text)
    return text
