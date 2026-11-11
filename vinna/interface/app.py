"""Ventana principal de VINNA.

Modelo de hilos (importante para que la ventana no se congele):

    Tkinter (hilo principal)            Hilo de trabajo (Worker)
    ------------------------            ------------------------
    usuario escribe y envía  ──cola──▶  orchestrator.handle(texto)
                                         (llamada lenta a Ollama/OpenAI)
    _poll() cada 50 ms       ◀──cola──  Reply / StatusEvent
    actualiza chat y ojos

Solo el hilo principal toca los widgets. El hilo de trabajo solo pone objetos
en una ``queue.Queue``, que es segura entre hilos.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import scrolledtext

from vinna.core.events import Reply, ReplyKind, StatusEvent
from vinna.core.orchestrator import Orchestrator
from vinna.interface.expressions import BACKGROUND, VisualState
from vinna.interface.face import Face

log = logging.getLogger(__name__)

POLL_MS = 50
_STATUS_REQUEST = object()  # petición interna: comprobar conexiones
_STOP = object()


class Worker(threading.Thread):
    """Un único hilo que procesa las peticiones en orden (sin condiciones de carrera)."""

    def __init__(self, orchestrator: Orchestrator, results: "queue.Queue[object]"):
        super().__init__(name="vinna-worker", daemon=True)
        self.orchestrator = orchestrator
        self.requests: "queue.Queue[object]" = queue.Queue()
        self.results = results

    def run(self) -> None:
        while True:
            item = self.requests.get()
            if item is _STOP:
                return
            try:
                if item is _STATUS_REQUEST:
                    self.results.put(self.orchestrator.connection_status())
                else:
                    reply = self.orchestrator.handle(str(item))
                    self.results.put(reply or Reply("", ReplyKind.COMMAND))
            except Exception:  # noqa: BLE001 - el hilo nunca debe morir
                log.exception("Error en el hilo de trabajo")
                self.results.put(Reply("Error inesperado. Revisa data/vinna.log.", ReplyKind.ERROR))

    def submit(self, item: object) -> None:
        self.requests.put(item)

    def stop(self) -> None:
        self.requests.put(_STOP)


class VinnaApp:
    def __init__(self, root: tk.Tk, orchestrator: Orchestrator):
        self.root = root
        self.orchestrator = orchestrator
        ui = orchestrator.settings.interface
        self.name = orchestrator.personality.name
        self.sleep_after = float(ui.get("sleep_after_minutes", 5)) * 60
        self.last_activity = time.monotonic()
        self.busy = False
        self._revert_job: str | None = None
        self._closing = False

        root.title(f"{self.name} · robot de escritorio")
        root.geometry(f"{ui['width']}x{ui['height']}")
        root.minsize(380, 520)
        root.configure(bg=BACKGROUND)
        self._build_widgets()

        self.results: "queue.Queue[object]" = queue.Queue()
        self.worker = Worker(orchestrator, self.results)
        self.worker.start()
        self.worker.submit(_STATUS_REQUEST)

        root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_job = root.after(POLL_MS, self._poll)
        self._sleep_job = root.after(5000, self._check_sleep)
        self._append("system", f"Hola, soy {self.name}. Escribe !ayuda para ver los comandos.")

    # ---------- construcción ----------
    def _build_widgets(self) -> None:
        self.face = Face(self.root, width=480, height=240)
        self.face.pack(fill="x", padx=10, pady=(10, 0))

        self.chat = scrolledtext.ScrolledText(
            self.root, wrap="word", state="disabled", height=12, bg="#121A21", fg="#ECEFF1",
            insertbackground="#ECEFF1", relief="flat", font=("Segoe UI", 10), padx=8, pady=6,
        )
        self.chat.pack(fill="both", expand=True, padx=10, pady=10)
        self.chat.tag_configure("user", foreground="#B3E5FC", spacing1=6)
        self.chat.tag_configure("assistant", foreground="#ECEFF1", spacing1=6)
        self.chat.tag_configure("command", foreground="#A5D6A7", spacing1=6)
        self.chat.tag_configure("error", foreground="#EF9A9A", spacing1=6)
        self.chat.tag_configure("system", foreground="#90A4AE", spacing1=6)
        self.chat.tag_configure("notice", foreground="#FFE082", spacing1=2)

        bottom = tk.Frame(self.root, bg=BACKGROUND)
        bottom.pack(fill="x", padx=10)
        self.entry = tk.Entry(bottom, font=("Segoe UI", 11), bg="#1C262F", fg="#ECEFF1",
                              insertbackground="#ECEFF1", relief="flat")
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.entry.bind("<Return>", lambda _e: self.send())
        self.entry.bind("<Key>", self._on_typing)
        self.send_button = tk.Button(bottom, text="Enviar", command=self.send, relief="flat",
                                     bg="#26A69A", fg="white", activebackground="#2BBBAD", padx=14)
        self.send_button.pack(side="left", padx=(8, 0))
        self.entry.focus_set()

        self.status_var = tk.StringVar(value="Comprobando conexión…")
        tk.Label(self.root, textvariable=self.status_var, anchor="w", bg=BACKGROUND, fg="#78909C",
                 font=("Segoe UI", 9)).pack(fill="x", padx=10, pady=(4, 8))

    # ---------- acciones del usuario ----------
    def send(self) -> None:
        text = self.entry.get().strip()
        if not text or self.busy:
            return
        self.entry.delete(0, "end")
        self._touch()
        self._append("user", f"Tú: {text}")
        self.busy = True
        self.send_button.configure(state="disabled")
        self._set_state(VisualState.THINKING)
        self.worker.submit(text)

    def _on_typing(self, event: tk.Event) -> None:
        self._touch()
        if self.busy or event.keysym == "Return":
            return
        self._set_state(VisualState.LISTENING, revert_ms=1500)

    # ---------- recepción de resultados (hilo principal) ----------
    def _poll(self) -> None:
        if self._closing:
            return
        try:
            while True:
                item = self.results.get_nowait()
                if isinstance(item, Reply):
                    self._show_reply(item)
                elif isinstance(item, StatusEvent):
                    self._show_status(item)
        except queue.Empty:
            pass
        self._poll_job = self.root.after(POLL_MS, self._poll)

    def _show_reply(self, reply: Reply) -> None:
        self.busy = False
        self.send_button.configure(state="normal")
        self._touch()
        if reply.notice:
            self._append("notice", f"⚠ {reply.notice}")
        if reply.kind is ReplyKind.ASSISTANT:
            source = {"local": "local", "cloud": "nube"}.get(reply.provider or "", reply.provider or "")
            self._append("assistant", f"{self.name} ({source}): {reply.text}")
            speak_ms = min(6000, 800 + 25 * len(reply.text))
            self._set_state(VisualState.SPEAKING, revert_ms=speak_ms)
        elif reply.kind is ReplyKind.COMMAND:
            if reply.text:
                self._append("command", reply.text)
            self._set_state(VisualState.IDLE)
        else:
            self._append("error", f"⚠ {reply.text}")
            self._set_state(VisualState.ERROR, revert_ms=3500)
        if reply.refresh_status:
            self.worker.submit(_STATUS_REQUEST)

    def _show_status(self, status: StatusEvent) -> None:
        local = "Ollama ✔" if status.local_ok else "Ollama ✘"
        cloud = "Nube ✔" if status.cloud_ok else "Nube ✘"
        self.status_var.set(f"Modo {status.mode}  ·  {local}  ·  {cloud}")
        if status.mode in ("LOCAL", "HYBRID") and not status.local_ok:
            self._append("error", f"⚠ {status.local_detail}")
        if status.mode == "CLOUD" and not status.cloud_ok:
            self._append("error", f"⚠ {status.cloud_detail}")

    # ---------- utilidades ----------
    def _append(self, tag: str, text: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", text + "\n", tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _set_state(self, state: VisualState, revert_ms: int | None = None) -> None:
        if self._revert_job is not None:
            self.root.after_cancel(self._revert_job)
            self._revert_job = None
        self.face.set_state(state)
        if revert_ms:
            self._revert_job = self.root.after(revert_ms, self._revert_to_idle)

    def _revert_to_idle(self) -> None:
        self._revert_job = None
        if not self.busy:
            self.face.set_state(VisualState.IDLE)

    def _touch(self) -> None:
        self.last_activity = time.monotonic()
        if self.face.visual_state is VisualState.SLEEPING:
            self.face.set_state(VisualState.IDLE)

    def _check_sleep(self) -> None:
        if self._closing:
            return
        idle = time.monotonic() - self.last_activity
        if not self.busy and idle >= self.sleep_after and self.face.visual_state is VisualState.IDLE:
            self.face.set_state(VisualState.SLEEPING)
        self._sleep_job = self.root.after(5000, self._check_sleep)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        for job in (self._poll_job, self._sleep_job, self._revert_job):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self.face.stop()
        self.worker.stop()
        self.root.destroy()
