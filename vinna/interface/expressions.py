"""Estados visuales de VINNA, su texto y la paleta de la carita de gato."""

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
    caption: str      # texto bajo el rostro


EXPRESSIONS: dict[VisualState, Expression] = {
    VisualState.IDLE: Expression(""),
    VisualState.LISTENING: Expression("Te escucho…"),
    VisualState.THINKING: Expression("Pensando…"),
    VisualState.SPEAKING: Expression(""),
    VisualState.SLEEPING: Expression("Descansando"),
    VisualState.ERROR: Expression("Algo salió mal"),
}

# Fondo de la "pantalla" del robot y colores del diseño.
BACKGROUND = "#140D22"
PALETTE = {
    "glow": "#3B2466",       # halo morado alrededor de cada trazo
    "ear": "#E6DAF7",        # lila de las orejas
    "ear_inner": "#F7A8D2",  # rosa del interior de las orejas
    "pink": "#F7A8D2",       # nariz y bigotes
    "white": "#FFFFFF",      # ojos y boca
    "sparkle": "#D6C8F2",    # brillitos de los ojos
    "blush": "#B04A86",      # chapitas
    "sweat": "#8FD3FF",      # gotita de sudor (error)
    "caption": "#A99BC4",
}

# Versión atenuada para cuando VINNA duerme.
PALETTE_DIM = {
    **PALETTE,
    "ear": "#9C8FB5",
    "ear_inner": "#A8729A",
    "pink": "#A8729A",
    "white": "#B9B0CC",
    "caption": "#7D7192",
}
