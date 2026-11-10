"""Pruebas de la interfaz (Pruebas 1 y 11).

Necesitan una pantalla. En Windows funcionan directamente; en Linux sin
pantalla se omiten salvo que se ejecuten con xvfb-run.
"""

from __future__ import annotations

import threading
import time

import pytest

tk = pytest.importorskip("tkinter")

from vinna.core.events import ReplyKind  # noqa: E402
from vinna.interface.expressions import VisualState  # noqa: E402
from tests.conftest import FakeProvider  # noqa: E402


class SlowProvider(FakeProvider):
    def __init__(self, *args, delay: float = 1.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.delay = delay
        self.started = threading.Event()

    def chat(self, messages):
        self.started.set()
        time.sleep(self.delay)
        return super().chat(messages)


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("No hay pantalla disponible")
    window.withdraw()
    yield window
    try:
        window.destroy()
    except tk.TclError:
        pass


def _pump(root, seconds: float, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        if until and until():
            return True
        time.sleep(0.01)
    return False


def test_window_opens_and_shows_states(root, build):  # Prueba 1
    from vinna.interface.app import VinnaApp

    orch, _, _ = build()
    app = VinnaApp(root, orch)
    for state in VisualState:
        app.face.set_state(state)
        root.update()
    app.close()


def test_ui_stays_responsive_while_model_thinks(root, build):  # Prueba 11
    from vinna.interface.app import VinnaApp

    slow = SlowProvider("local", "listo", delay=1.0)
    orch, _, _ = build(local=slow)
    app = VinnaApp(root, orch)
    app.entry.insert(0, "hola")
    app.send()
    assert app.face.visual_state is VisualState.THINKING
    assert slow.started.wait(2)

    # Mientras el modelo "piensa", el bucle de Tkinter debe seguir procesando eventos.
    ticks = []
    root.after(10, lambda: ticks.append(1))
    root.after(50, lambda: ticks.append(2))
    _pump(root, 0.3)
    assert ticks == [1, 2] and app.busy

    done = _pump(root, 3, until=lambda: not app.busy)
    assert done
    assert "listo" in app.chat.get("1.0", "end")
    assert app.face.visual_state is VisualState.SPEAKING
    assert orch.short_term.count() == 2
    app.close()


def test_errors_are_shown_without_closing(root, build):  # Prueba 12
    from vinna.interface.app import VinnaApp

    orch, _, _ = build(local=FakeProvider("local", fail="Ollama no está disponible"))
    app = VinnaApp(root, orch)
    app.entry.insert(0, "hola")
    app.send()
    assert _pump(root, 3, until=lambda: not app.busy)
    assert "Ollama no está disponible" in app.chat.get("1.0", "end")
    assert app.face.visual_state is VisualState.ERROR
    app.close()


def test_reply_kind_enum_is_stable():
    assert ReplyKind("assistant") is ReplyKind.ASSISTANT
