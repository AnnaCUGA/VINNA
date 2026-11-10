"""Eventos que viajan del hilo de trabajo a la interfaz mediante una cola.

La interfaz nunca llama al modelo directamente: envía la petición a un hilo
de trabajo y recibe estos eventos, que procesa en el hilo principal de Tkinter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReplyKind(str, Enum):
    ASSISTANT = "assistant"  # respuesta del modelo
    COMMAND = "command"      # resultado de un comando interno
    ERROR = "error"          # fallo comprensible para el usuario


@dataclass(frozen=True)
class Reply:
    text: str
    kind: ReplyKind
    provider: str | None = None
    notice: str | None = None        # p. ej. aviso de respaldo híbrido
    refresh_status: bool = False


@dataclass(frozen=True)
class StatusEvent:
    """Resumen de conexión para la barra de estado."""

    mode: str
    local_ok: bool
    local_detail: str
    cloud_ok: bool
    cloud_detail: str
