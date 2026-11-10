"""Rostro digital de VINNA: dos ojos dibujados en un Canvas de Tkinter.

Las animaciones son ligeras: se redibujan unas pocas figuras cada ~80 ms solo
mientras el estado lo necesita. Todo este código se ejecuta en el hilo principal
de Tkinter (``set_state`` debe llamarse desde ese hilo).
"""

from __future__ import annotations

import math
import random
import tkinter as tk

from vinna.interface.expressions import BACKGROUND, EXPRESSIONS, VisualState

FRAME_MS = 80


class Face(tk.Canvas):
    def __init__(self, master: tk.Misc, width: int = 480, height: int = 260):
        super().__init__(master, width=width, height=height, bg=BACKGROUND, highlightthickness=0)
        self.visual_state = VisualState.IDLE
        self._tick = 0
        self._job: str | None = None
        self._next_blink = self._random_blink()
        self._blink_frames = 0
        self.bind("<Configure>", lambda _e: self.redraw())
        self._schedule()

    # ---------- API ----------
    def set_state(self, state: VisualState) -> None:
        if state is self.visual_state:
            return
        self.visual_state = state
        self._tick = 0
        self._blink_frames = 0
        self.redraw()
        self._schedule()

    def stop(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    # ---------- animación ----------
    @staticmethod
    def _random_blink() -> int:
        return random.randint(30, 70)  # en frames (≈ 2.5–5.5 s)

    def _schedule(self) -> None:
        self.stop()
        if EXPRESSIONS[self.visual_state].animated:
            self._job = self.after(FRAME_MS, self._animate)

    def _animate(self) -> None:
        self._job = None
        self._tick += 1
        if self.visual_state is VisualState.IDLE:
            if self._blink_frames:
                self._blink_frames -= 1
            elif self._tick >= self._next_blink:
                self._blink_frames = 3
                self._tick = 0
                self._next_blink = self._random_blink()
        self.redraw()
        self._schedule()

    # ---------- dibujo ----------
    def redraw(self) -> None:
        self.delete("face")
        w = max(self.winfo_width(), int(self["width"]))
        h = max(self.winfo_height(), int(self["height"]))
        expr = EXPRESSIONS[self.visual_state]
        cx_left, cx_right, cy = w * 0.32, w * 0.68, h * 0.44
        rx, ry = w * 0.10, h * 0.24 * expr.openness
        shift_x = shift_y = 0.0

        if self.visual_state is VisualState.IDLE and self._blink_frames:
            ry = h * 0.02
        elif self.visual_state is VisualState.THINKING:
            angle = self._tick * 0.25
            shift_x, shift_y = math.cos(angle) * w * 0.03, -abs(math.sin(angle)) * h * 0.04 - h * 0.03
        elif self.visual_state is VisualState.LISTENING:
            ry *= 1 + 0.04 * math.sin(self._tick * 0.4)

        for cx in (cx_left, cx_right):
            x, y = cx + shift_x, cy + shift_y
            if self.visual_state is VisualState.SLEEPING:
                self.create_line(x - rx, y, x + rx, y, fill=expr.color, width=6, capstyle="round", tags="face")
            elif self.visual_state is VisualState.ERROR:
                d = rx * 0.8
                for sx in (-1, 1):
                    self.create_line(x - d, y - d * sx, x + d, y + d * sx, fill=expr.color, width=8,
                                     capstyle="round", tags="face")
            else:
                self.create_oval(x - rx, y - ry, x + rx, y + ry, fill=expr.color, outline="", tags="face")

        if self.visual_state is VisualState.SPEAKING:
            mouth_w = w * (0.06 + 0.05 * abs(math.sin(self._tick * 0.6)))
            my = h * 0.80
            self.create_line(w / 2 - mouth_w, my, w / 2 + mouth_w, my, fill=expr.color, width=6,
                             capstyle="round", tags="face")
        if self.visual_state is VisualState.SLEEPING:
            phase = (self._tick % 30) / 30
            self.create_text(w * 0.82, h * (0.30 - 0.12 * phase), text="z", fill=expr.color,
                             font=("Helvetica", int(14 + 10 * phase), "bold"), tags="face")
        if expr.caption:
            self.create_text(w / 2, h * 0.93, text=expr.caption, fill="#90A4AE",
                             font=("Helvetica", 11), tags="face")
