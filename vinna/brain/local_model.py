"""Cliente del modelo local (Ollama).

Usa la API HTTP de Ollama con la biblioteca estándar (urllib), así el modo local
no necesita dependencias extra. Documentación de la API:
https://github.com/ollama/ollama/blob/main/docs/api.md
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from vinna.brain.base import ChatMessages, ProviderError


class OllamaClient:
    name = "local"

    def __init__(self, host: str, model: str, timeout: float = 120, temperature: float | None = 0.7):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    @property
    def label(self) -> str:
        return f"Ollama ({self.model})"

    def is_configured(self) -> bool:
        return bool(self.host and self.model)

    # ---------- HTTP ----------
    def _request(self, path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        url = f"{self.host}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", "")
            except Exception:  # noqa: BLE001 - el cuerpo puede no ser JSON
                pass
            if exc.code == 404 and "not found" in detail.lower():
                raise ProviderError(
                    f"El modelo '{self.model}' no está instalado en Ollama. "
                    f"Instálalo con:  ollama pull {self.model}",
                    self.name,
                ) from exc
            raise ProviderError(f"Ollama respondió con error {exc.code}: {detail or exc.reason}", self.name) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderError(
                f"Ollama tardó demasiado en responder (más de {timeout or self.timeout:.0f} s).", self.name
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderError("Ollama tardó demasiado en responder.", self.name) from exc
            raise ProviderError(
                f"No se pudo conectar con Ollama en {self.host}. "
                "Comprueba que Ollama esté abierto (o ejecuta:  ollama serve).",
                self.name,
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("Ollama devolvió una respuesta que no se pudo interpretar.", self.name) from exc

    # ---------- API pública ----------
    def check(self) -> tuple[bool, str]:
        try:
            data = self._request("/api/tags", timeout=5)
        except ProviderError as exc:
            return False, str(exc)
        names = {m.get("name", "") for m in data.get("models", [])}
        wanted = {self.model, f"{self.model}:latest"}
        if names & wanted:
            return True, f"Ollama conectado, modelo {self.model} disponible."
        return False, f"Ollama está activo pero falta el modelo. Ejecuta:  ollama pull {self.model}"

    def chat(self, messages: ChatMessages) -> str:
        payload: dict = {"model": self.model, "messages": messages, "stream": False}
        if self.temperature is not None:
            payload["options"] = {"temperature": self.temperature}
        data = self._request("/api/chat", payload)
        content = (data.get("message") or {}).get("content", "")
        if not content.strip():
            raise ProviderError("El modelo local devolvió una respuesta vacía.", self.name)
        return content.strip()
