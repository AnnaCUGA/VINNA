"""Utilidades compartidas por las pruebas.

Las pruebas no necesitan Ollama ni Internet: usan proveedores falsos y un
pequeño servidor HTTP local que imita la API de Ollama.
"""

from __future__ import annotations

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from vinna.brain.base import ProviderError
from vinna.brain.model_router import Mode, ModelRouter
from vinna.config import DEFAULT_SETTINGS, Settings
from vinna.core.orchestrator import Orchestrator
from vinna.memory.database import Database
from vinna.personality.character import Personality


class FakeProvider:
    """Proveedor de IA simulado que registra los mensajes recibidos."""

    def __init__(self, name: str, reply: str = "respuesta", fail: str | None = None, configured: bool = True):
        self.name = name
        self.label = f"Fake-{name}"
        self.reply = reply
        self.fail = fail
        self.configured = configured
        self.calls: list[list[dict]] = []

    def is_configured(self) -> bool:
        return self.configured

    def check(self):
        return (self.fail is None and self.configured, "fake")

    def chat(self, messages):
        self.calls.append(messages)
        if self.fail:
            raise ProviderError(self.fail, self.name)
        return self.reply


def make_settings(tmp_path, **overrides) -> Settings:
    raw = copy.deepcopy(DEFAULT_SETTINGS)
    raw["memory"]["database"] = str(tmp_path / "vinna.db")
    for dotted, value in overrides.items():
        node = raw
        *parents, last = dotted.split("__")
        for p in parents:
            node = node[p]
        node[last] = value
    return Settings(raw=raw, root=tmp_path)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def build(tmp_path):
    """Fábrica: crea un orquestador con proveedores falsos y base de datos temporal."""
    created: list[Database] = []

    def _build(local=None, cloud=None, mode=Mode.LOCAL, **setting_overrides):
        s = make_settings(tmp_path, **setting_overrides)
        local = local or FakeProvider("local", "hola desde local")
        cloud = cloud or FakeProvider("cloud", "hola desde la nube")
        router = ModelRouter(local, cloud, mode, complex_tasks_to_cloud=False)
        db = Database(s.database_path)
        created.append(db)
        return Orchestrator(s, Personality(), db, router), local, cloud

    yield _build
    for db in created:
        db.close()


# ---------- servidor que imita a Ollama ----------
class _OllamaHandler(BaseHTTPRequestHandler):
    models = ["qwen2.5:0.5b"]
    received: list[dict] = []

    def log_message(self, *args):  # silencio en las pruebas
        pass

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": m} for m in self.models]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).received.append(body)
        if body["model"] not in self.models:
            self._send(404, {"error": f"model \"{body['model']}\" not found, try pulling it first"})
            return
        last = body["messages"][-1]["content"]
        self._send(200, {"message": {"role": "assistant", "content": f"eco: {last}"}, "done": True})


@pytest.fixture
def fake_ollama():
    _OllamaHandler.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", _OllamaHandler
    server.shutdown()
    server.server_close()
