"""Enrutador de modelos: decide qué proveedor (local o nube) responde.

Modos:
- LOCAL:  solo el modelo local. Si falla se informa el error (sin respaldo).
- CLOUD:  solo la nube. Si falla se informa el error (sin respaldo).
- HYBRID: elige el proveedor según la configuración y el tipo de tarea; si el
          elegido falla, usa el otro y lo AVISA (nunca cambia en silencio).

El enrutador recibe una función ``build_messages(provider)`` en lugar de una lista
fija, para que el orquestador pueda aplicar políticas de privacidad por
proveedor (por ejemplo, no enviar recuerdos a la nube).
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Callable

from vinna.brain.base import ChatMessages, ChatProvider, ModelResult, ProviderError

log = logging.getLogger(__name__)

COMPLEX_HINTS = (
    "analiza", "análisis", "explica en detalle", "compara", "paso a paso", "redacta",
    "resume este", "código", "programa", "investiga", "planifica", "calcula",
)

MODE_ALIASES = {
    "local": "LOCAL", "nube": "CLOUD", "cloud": "CLOUD",
    "hibrido": "HYBRID", "híbrido": "HYBRID", "hybrid": "HYBRID",
}


class Mode(str, Enum):
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"
    HYBRID = "HYBRID"

    @classmethod
    def parse(cls, value: str) -> "Mode":
        key = (value or "").strip()
        normalized = MODE_ALIASES.get(key.lower(), key.upper())
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"Modo desconocido: '{value}'. Usa local, nube o hibrido.") from exc


class RouterError(Exception):
    """Ningún proveedor permitido pudo responder. Mensaje listo para el usuario."""


class ModelRouter:
    def __init__(
        self,
        local: ChatProvider,
        cloud: ChatProvider,
        mode: Mode | str = Mode.LOCAL,
        hybrid_prefer: str = "local",
        complex_tasks_to_cloud: bool = True,
        complex_min_chars: int = 400,
    ):
        self.providers = {"local": local, "cloud": cloud}
        self.mode = Mode.parse(mode) if isinstance(mode, str) else mode
        self.hybrid_prefer = "cloud" if str(hybrid_prefer).lower() == "cloud" else "local"
        self.complex_tasks_to_cloud = complex_tasks_to_cloud
        self.complex_min_chars = complex_min_chars

    def set_mode(self, mode: Mode | str) -> Mode:
        self.mode = Mode.parse(mode) if isinstance(mode, str) else mode
        log.info("Modo de IA cambiado a %s", self.mode.value)
        return self.mode

    def is_complex(self, text: str) -> bool:
        lowered = text.lower()
        return len(text) >= self.complex_min_chars or any(h in lowered for h in COMPLEX_HINTS)

    def plan(self, text: str) -> list[str]:
        """Orden de proveedores a intentar para este mensaje."""
        if self.mode is Mode.LOCAL:
            return ["local"]
        if self.mode is Mode.CLOUD:
            return ["cloud"]
        first = self.hybrid_prefer
        if self.complex_tasks_to_cloud and self.is_complex(text):
            first = "cloud"
        order = [first, "local" if first == "cloud" else "cloud"]
        # En híbrido no tiene sentido intentar la nube si no hay clave configurada.
        return [p for p in order if self.providers[p].is_configured()] or ["local"]

    def generate(self, text: str, build_messages: Callable[[str], ChatMessages]) -> ModelResult:
        errors: list[str] = []
        for name in self.plan(text):
            provider = self.providers[name]
            try:
                answer = provider.chat(build_messages(name))
            except ProviderError as exc:
                log.warning("Proveedor %s falló: %s", name, exc)
                errors.append(f"{provider.label}: {exc}")
                continue
            notice = None
            if errors:
                notice = f"Usé {provider.label} como respaldo porque falló el otro proveedor. ({errors[0]})"
            return ModelResult(text=answer, provider=name, fallback_notice=notice)
        if len(errors) == 1:
            raise RouterError(errors[0].split(": ", 1)[1])
        raise RouterError("Ningún modelo pudo responder:\n- " + "\n- ".join(errors))

    def status(self) -> dict[str, tuple[bool, str]]:
        """Comprueba la disponibilidad de cada proveedor (puede tardar unos segundos)."""
        return {name: p.check() for name, p in self.providers.items()}
