"""Rostro digital de VINNA: carita de gato animada en un Canvas de Tkinter.

Diseño: orejas lilas con interior rosa, ojos blancos, nariz rosa, boca "ω" y
bigotes rosas, todo con un halo morado.

La animación depende del tiempo real (no de contar cuadros): respiración,
parpadeos, miradas, movimientos de orejas y efectos propios de cada estado.
Se redibuja cada ~50 ms con figuras sencillas, sin imágenes, para que sea
ligera. Todo este código se ejecuta en el hilo principal de Tkinter.
"""

from __future__ import annotations

import math
import random
import time
import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable

from vinna.interface.expressions import BACKGROUND, EXPRESSIONS, PALETTE, PALETTE_DIM, VisualState

FRAME_MS = 50

# ---------- geometría (coordenadas normalizadas 0–1, proporción 2:1) ----------
EAR_STROKE = [(0.085, 0.46), (0.088, 0.30), (0.105, 0.17), (0.14, 0.15), (0.20, 0.19), (0.265, 0.27)]
EAR_INNER = [(0.125, 0.40), (0.128, 0.30), (0.14, 0.215), (0.17, 0.225), (0.235, 0.29), (0.18, 0.33)]
EAR_PIVOT = (0.17, 0.42)
EYE_X, EYE_Y = 0.31, 0.60
EYE_RX, EYE_RY = 0.048, 0.115
NOSE_Y = 0.665
MOUTH_TOP = 0.68  # punto donde se unen los dos lóbulos de la ω
WHISKERS = [((0.07, 0.655), (0.17, 0.675)), ((0.08, 0.775), (0.17, 0.74))]
FACE_CENTER = (0.5, 0.55)
FACE_SCALE = 0.9  # deja margen a los lados para las ondas y los efectos


def _ease(p: float) -> float:
    p = max(0.0, min(1.0, p))
    return p * p * (3 - 2 * p)


def _rotate(points, pivot, degrees):
    a = math.radians(degrees)
    px, py = pivot
    c, s = math.cos(a), math.sin(a)
    return [(px + (x - px) * c - (y - py) * s, py + (x - px) * s + (y - py) * c) for x, y in points]


def _arc_points(cx, cy, rx, ry, a0, a1, n=18):
    """Puntos de un arco de elipse; ángulos en grados, 0 = derecha, 90 = arriba."""
    out = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        out.append((cx + rx * math.cos(a), cy - ry * math.sin(a)))
    return out


@dataclass
class Pose:
    """Todo lo que define un cuadro de la animación."""

    dx: float = 0.0          # desplazamiento de toda la cara
    dy: float = 0.0
    tilt: float = 0.0        # inclinación de la cabeza (grados)
    ear_l: float = 0.0       # inclinación de cada oreja (+ hacia adentro, - caída)
    ear_r: float = 0.0
    ear_lift: float = 0.0
    eyes: str = "open"       # open | happy | closed | error
    eye_scale: float = 1.0
    look_x: float = 0.0
    look_y: float = 0.0
    lid_top: float = 0.0     # 0 abierto … 1 cerrado
    lid_bottom: float = 0.0
    mouth_open: float = 0.0
    blush: bool = False
    whisker_wiggle: float = 0.0
    extras: list[str] = field(default_factory=list)


class Face(tk.Canvas):
    def __init__(self, master: tk.Misc, width: int = 480, height: int = 240,
                 clock: Callable[[], float] = time.monotonic, rng: random.Random | None = None):
        super().__init__(master, width=width, height=height, bg=BACKGROUND, highlightthickness=0)
        self._clock = clock
        self._rng = rng or random.Random()
        self.visual_state = VisualState.IDLE
        now = clock()
        self._state_start = now
        self._job: str | None = None
        # comportamiento espontáneo
        self._blink_at = now + self._rng.uniform(1.5, 4.0)
        self._blink_start = -10.0
        self._double_blink = False
        self._look_from = (0.0, 0.0)
        self._look_to = (0.0, 0.0)
        self._look_start = now
        self._look_next = now + self._rng.uniform(1.0, 3.0)
        self._twitch_at = now + self._rng.uniform(3.0, 7.0)
        self._twitch_start = -10.0
        self._twitch_side = 0
        self.bind("<Configure>", lambda _e: self.redraw())
        self._schedule()

    # ---------- API ----------
    def set_state(self, state: VisualState) -> None:
        if state is self.visual_state:
            return
        self.visual_state = state
        self._state_start = self._clock()
        self.redraw()

    def stop(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _schedule(self) -> None:
        self._job = self.after(FRAME_MS, self._animate)

    def _animate(self) -> None:
        self._job = None
        self.redraw()
        self._schedule()

    # ---------- comportamiento espontáneo ----------
    def _blink_amount(self, now: float) -> float:
        if now >= self._blink_at:
            self._blink_start = now
            self._double_blink = self._rng.random() < 0.2
            self._blink_at = now + self._rng.uniform(2.0, 5.5)
        p = now - self._blink_start
        duration = 0.36 if self._double_blink else 0.18
        if p < 0 or p > duration:
            return 0.0
        p = (p % 0.18) / 0.18
        return 1 - abs(2 * p - 1)  # 0 → 1 → 0

    def _glance(self, now: float) -> tuple[float, float]:
        if now >= self._look_next:
            self._look_from = self._current_look(now)
            if self._rng.random() < 0.35:
                self._look_to = (0.0, 0.0)
            else:
                self._look_to = (self._rng.uniform(-0.035, 0.035), self._rng.uniform(-0.025, 0.02))
            self._look_start = now
            self._look_next = now + self._rng.uniform(1.2, 3.5)
        return self._current_look(now)

    def _current_look(self, now: float) -> tuple[float, float]:
        k = _ease((now - self._look_start) / 0.25)
        (x0, y0), (x1, y1) = self._look_from, self._look_to
        return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k

    def _ear_twitch(self, now: float) -> tuple[float, float]:
        if now >= self._twitch_at:
            self._twitch_start = now
            self._twitch_side = self._rng.choice((0, 1))
            self._twitch_at = now + self._rng.uniform(4.0, 9.0)
        p = (now - self._twitch_start) / 0.45
        if not 0 <= p <= 1:
            return 0.0, 0.0
        amount = 14 * math.sin(p * math.pi * 3) * (1 - p)
        return (amount, 0.0) if self._twitch_side == 0 else (0.0, amount)

    # ---------- poses por estado ----------
    def _pose(self, now: float) -> Pose:
        s = self.visual_state
        t = now - self._state_start
        if s is VisualState.IDLE:
            lx, ly = self._glance(now)
            tl, tr = self._ear_twitch(now)
            return Pose(dy=0.008 * math.sin(now * 2 * math.pi / 3.6), ear_l=tl, ear_r=tr,
                        look_x=lx, look_y=ly, lid_top=self._blink_amount(now))
        if s is VisualState.LISTENING:
            wiggle = 5 * math.sin(t * 9) if (t % 1.4) < 0.5 else 0.0
            return Pose(dy=-0.01, tilt=4 * _ease(t / 0.4), ear_l=6 + wiggle, ear_r=6 - wiggle,
                        ear_lift=0.025, eye_scale=1.18, lid_top=self._blink_amount(now) * 0.8,
                        blush=True, extras=["waves"])
        if s is VisualState.THINKING:
            drift = 0.03 * math.sin(t * 1.6)
            return Pose(tilt=-6 * _ease(t / 0.4), dy=0.005 * math.sin(t * 2.2), ear_l=-6, ear_r=12,
                        look_x=0.025 + drift, look_y=-0.035, lid_top=0.22, eye_scale=0.9, extras=["dots"])
        if s is VisualState.SPEAKING:
            syllable = abs(math.sin(t * 9)) * (0.55 + 0.45 * math.sin(t * 2.3))
            bob = math.sin(t * 4.5)
            return Pose(dy=-0.012 * abs(bob), eyes="happy", mouth_open=syllable, blush=True,
                        whisker_wiggle=0.01 * math.sin(t * 9), ear_l=3 * bob, ear_r=3 * bob)
        if s is VisualState.SLEEPING:
            breath = math.sin(now * 2 * math.pi / 4.5)
            return Pose(dy=0.03 + 0.018 * breath, tilt=3, ear_l=-16 + 2 * breath, ear_r=-16 + 2 * breath,
                        ear_lift=-0.04, eyes="closed", extras=["zzz"])
        # ERROR: sacudida breve, orejas caídas y gotita de sudor
        shake = 0.014 * math.sin(t * 45) * math.exp(-t * 3.5)
        return Pose(dx=shake, ear_l=-22, ear_r=-22, ear_lift=-0.03, eyes="error", extras=["sweat"])

    # ---------- transformación y primitivas ----------
    def _layout(self) -> None:
        w = max(self.winfo_width(), int(self["width"]))
        h = max(self.winfo_height(), int(self["height"]))
        self._fw = min(w, h * 2)
        self._fh = self._fw / 2
        self._ox, self._oy = (w - self._fw) / 2, (h - self._fh) / 2
        self._stroke = max(3.0, self._fw * 0.022)
        self._halo = max(2.0, self._fw * 0.016)

    def _pt(self, x: float, y: float) -> tuple[float, float]:
        p = self._p
        if p.tilt:
            (x, y), = _rotate([(x, y)], FACE_CENTER, p.tilt)
        x, y = 0.5 + (x - 0.5) * FACE_SCALE, 0.5 + (y - 0.5) * FACE_SCALE
        return self._ox + (x + p.dx) * self._fw, self._oy + (y + p.dy) * self._fh

    def _flat(self, points) -> list[float]:
        return [c for pt in points for c in self._pt(*pt)]

    def _curve(self, points, color, width, glow=True, halo=None):
        coords = self._flat(points)
        if glow:
            self.create_line(coords, fill=self._pal["glow"], width=width + (self._halo if halo is None else halo),
                             smooth=True,
                             capstyle="round", joinstyle="round", tags="face")
        self.create_line(coords, fill=color, width=width, smooth=True, capstyle="round",
                         joinstyle="round", tags="face")

    def _shape(self, points, fill, outline=True, smooth=False, width=None):
        self.create_polygon(self._flat(points), fill=fill, smooth=smooth,
                            outline=self._pal["glow"] if outline else "",
                            width=(self._halo if width is None else width) if outline else 0,
                            joinstyle="round", tags="face")

    @staticmethod
    def _ellipse(cx, cy, rx, ry, n=28):
        return _arc_points(cx, cy, rx, ry, 0, 360, n)[:-1]

    # ---------- partes ----------
    def _draw_ears(self, p: Pose):
        for side, tilt in ((0, p.ear_l), (1, p.ear_r)):
            stroke = [(x, y - p.ear_lift) for x, y in _rotate(EAR_STROKE, EAR_PIVOT, tilt)]
            inner = [(x, y - p.ear_lift) for x, y in _rotate(EAR_INNER, EAR_PIVOT, tilt)]
            if side:
                stroke = [(1 - x, y) for x, y in stroke]
                inner = [(1 - x, y) for x, y in inner]
            self._shape(inner, self._pal["ear_inner"], outline=False, smooth=True)
            self._curve(stroke, self._pal["ear"], self._stroke * 1.3)

    def _draw_eye(self, cx: float, p: Pose):
        cy = EYE_Y
        rx, ry = EYE_RX * p.eye_scale, EYE_RY * p.eye_scale
        white = self._pal["white"]
        if p.eyes == "happy":  # ^ ^
            self._curve(_arc_points(cx, cy + 0.06, 0.07, 0.11, 25, 155), white, self._stroke)
            return
        if p.eyes == "closed":  # ‿ ‿
            self._curve(_arc_points(cx, cy - 0.03, 0.06, 0.07, 205, 335), white, self._stroke)
            return
        if p.eyes == "error":  # > <
            s = 1 if cx < 0.5 else -1
            self._curve([(cx - 0.05 * s, cy - 0.095), (cx + 0.045 * s, cy), (cx - 0.05 * s, cy + 0.095)],
                        white, self._stroke * 1.1)
            return
        cx += p.look_x
        cy += p.look_y
        top = cy - ry + 2 * ry * p.lid_top
        bottom = cy + ry - 2 * ry * p.lid_bottom
        if bottom - top < ry * 0.18:  # parpadeo: línea
            mid = (top + bottom) / 2
            self._curve([(cx - rx * 1.1, mid), (cx + rx * 1.1, mid)], white, self._stroke)
            return
        pts = [(x, min(max(y, top), bottom)) for x, y in self._ellipse(cx, cy, rx, ry)]
        self._shape(pts, white)
        if p.lid_top < 0.35:  # brillitos
            self._shape(self._ellipse(cx + rx * 0.35, cy - ry * 0.4, rx * 0.28, ry * 0.18, 12),
                        self._pal["sparkle"], outline=False)
            self._shape(self._ellipse(cx - rx * 0.3, cy + ry * 0.35, rx * 0.12, ry * 0.08, 10),
                        self._pal["sparkle"], outline=False)

    def _draw_mouth(self, p: Pose):
        """Nariz rosa y boquita "ω" de un solo trazo; al hablar, la ω se estira y se encoge."""
        rx = 0.037 * (1 + 0.08 * p.mouth_open)
        ry = 0.06 * (1 + 0.7 * p.mouth_open)
        top = MOUTH_TOP
        w_line = (_arc_points(0.5 - rx, top, rx, ry, 180, 360, 12)
                  + _arc_points(0.5 + rx, top, rx, ry, 180, 360, 12)[1:])
        self._curve(w_line, self._pal["white"], self._stroke * 0.85)
        nose = [(0.472, NOSE_Y - 0.04), (0.528, NOSE_Y - 0.04), (0.531, NOSE_Y - 0.015), (0.5, NOSE_Y + 0.03),
                (0.469, NOSE_Y - 0.015)]
        self._shape(nose, self._pal["pink"], smooth=True, width=self._halo * 0.5)

    def _draw_whiskers(self, p: Pose):
        for a, b in WHISKERS:
            a2 = (a[0], a[1] + p.whisker_wiggle)
            self._curve([a2, b], self._pal["pink"], self._stroke * 0.7)
            self._curve([(1 - a2[0], a2[1]), (1 - b[0], b[1])], self._pal["pink"], self._stroke * 0.7)

    def _draw_blush(self):
        for cx in (EYE_X - 0.065, 1 - EYE_X + 0.065):
            self._shape(self._ellipse(cx, EYE_Y + 0.15, 0.04, 0.035, 16), self._pal["blush"], outline=False)

    def _draw_extras(self, p: Pose, now: float):
        t = now - self._state_start
        if "waves" in p.extras:  # ondas de sonido junto a las orejas
            for side in (0, 1):
                for i in range(3):
                    phase = (t * 1.3 + i / 3) % 1.0
                    if phase > 0.85:
                        continue
                    r = 0.04 + 0.07 * phase
                    cx = 0.0 if side == 0 else 1.0
                    a0, a1 = (125, 235) if side == 0 else (-55, 55)
                    pts = _arc_points(cx, 0.30, r * 0.33, r, a0, a1, 10)
                    self._curve(pts, self._pal["ear"], max(2.0, self._stroke * (0.9 - 0.6 * phase)))
        if "dots" in p.extras:  # • • • pensando
            for i in range(3):
                bounce = max(0.0, math.sin(t * 5 - i * 0.8)) * 0.035
                self._shape(self._ellipse(0.44 + i * 0.06, 0.13 - bounce, 0.014, 0.028, 12), self._pal["white"])
        if "zzz" in p.extras:
            for i in range(3):
                phase = (t * 0.35 + i / 3) % 1.0
                x, y = self._pt(0.56 + 0.12 * phase, 0.42 - 0.32 * phase)
                size = max(6, int(self._fw * (0.022 + 0.03 * phase)))
                self.create_text(x, y, text="z", fill=self._pal["ear"], font=("Helvetica", size, "bold"), tags="face")
        if "sweat" in p.extras:
            y0 = 0.40 + min(t, 1.2) * 0.04
            cx = 0.83
            pts = [(cx, y0 - 0.07), (cx + 0.022, y0), (cx + 0.016, y0 + 0.03), (cx, y0 + 0.04),
                   (cx - 0.016, y0 + 0.03), (cx - 0.022, y0)]
            self._shape(pts, self._pal["sweat"], smooth=True)

    # ---------- dibujo ----------
    def redraw(self) -> None:
        self.delete("face")
        now = self._clock()
        self._layout()
        self._p = self._pose(now)
        self._pal = PALETTE_DIM if self.visual_state is VisualState.SLEEPING else PALETTE
        if self._p.blush:
            self._draw_blush()
        self._draw_ears(self._p)
        self._draw_whiskers(self._p)
        for cx in (EYE_X, 1 - EYE_X):
            self._draw_eye(cx, self._p)
        self._draw_mouth(self._p)
        self._draw_extras(self._p, now)
        caption = EXPRESSIONS[self.visual_state].caption
        if caption:
            self.create_text(self._ox + 0.5 * self._fw, self._oy + 0.95 * self._fh, text=caption,
                             fill=self._pal["caption"], font=("Helvetica", 11), tags="face")
