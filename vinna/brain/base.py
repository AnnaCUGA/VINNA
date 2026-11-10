"""Tipos comunes a los proveedores de IA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

ChatMessages = list[dict[str, str]]  # [{"role": "system"|"user"|"assistant", "content": "..."}]


class ProviderError(Exception):
    """Fallo de un proveedor de IA. ``str(error)`` es un mensaje comprensible en español."""

    def __init__(self, message: str, provider: str = ""):
        super().__init__(message)
        self.provider = provider


class ChatProvider(Protocol):
    name: str  # 'local' | 'cloud'
    label: str  # texto para mostrar, p. ej. "Ollama (qwen2.5:0.5b)"

    def is_configured(self) -> bool: ...

    def check(self) -> tuple[bool, str]:
        """Comprueba disponibilidad real. Devuelve (ok, descripción)."""
        ...

    def chat(self, messages: ChatMessages) -> str: ...


@dataclass(frozen=True)
class ModelResult:
    text: str
    provider: str  # proveedor que respondió
    fallback_notice: str | None = None  # explicación si se usó el respaldo
