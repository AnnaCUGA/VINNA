"""Estados visuales de VINNA y la apariencia de cada uno."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VisualState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    SLEEPING = "SLEEPING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Expression:
    color: str        # color de los ojos
    openness: float   # 1.0 = ojo normal; <1 entrecerrado; >1 muy abierto
    caption: str      # texto bajo el rostro
    animated: bool    # si necesita refrescos periódicos


EXPRESSIONS: dict[VisualState, Expression] = {
    VisualState.IDLE: Expression("#4FC3F7", 1.0, "", True),            # parpadeo ocasional
    VisualState.LISTENING: Expression("#81C784", 1.15, "Te escucho…", True),
    VisualState.THINKING: Expression("#FFD54F", 0.75, "Pensando…", True),
    VisualState.SPEAKING: Expression("#4FC3F7", 1.0, "", True),
    VisualState.SLEEPING: Expression("#546E7A", 0.0, "Descansando", True),
    VisualState.ERROR: Expression("#E57373", 1.0, "Algo salió mal", False),
}

BACKGROUND = "#0B1015"
