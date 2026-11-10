"""Cliente opcional del modelo en la nube (OpenAI).

La biblioteca ``openai`` se importa solo cuando se usa, para que VINNA funcione
en modo local sin tenerla instalada (ver requirements-cloud.txt).
La clave API se lee de la variable de entorno OPENAI_API_KEY y nunca se guarda
ni se muestra.
"""

from __future__ import annotations

from vinna.brain.base import ChatMessages, ProviderError


class OpenAIClient:
    name = "cloud"

    def __init__(self, api_key: str | None, model: str, timeout: float = 60, temperature: float | None = None):
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self._client = None

    @property
    def label(self) -> str:
        return f"OpenAI ({self.model})"

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if not self._api_key:
            raise ProviderError(
                "OpenAI no está configurado: falta OPENAI_API_KEY en el archivo .env.", self.name
            )
        if self._client is None:
            try:
                from openai import OpenAI  # import diferido (dependencia opcional)
            except ImportError as exc:
                raise ProviderError(
                    "Falta la biblioteca de OpenAI. Instálala con:  pip install -r requirements-cloud.txt",
                    self.name,
                ) from exc
            self._client = OpenAI(api_key=self._api_key, timeout=self.timeout, max_retries=1)
        return self._client

    def check(self) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "OpenAI no configurado (sin OPENAI_API_KEY)."
        try:
            self._get_client()
        except ProviderError as exc:
            return False, str(exc)
        # No se hace una llamada real para no consumir saldo al arrancar.
        return True, f"OpenAI configurado ({self.model})."

    def chat(self, messages: ChatMessages) -> str:
        client = self._get_client()
        kwargs: dict = {"model": self.model, "messages": messages}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - se traduce a un error comprensible
            raise ProviderError(_describe_openai_error(exc), self.name) from exc
        content = (response.choices[0].message.content or "").strip() if response.choices else ""
        if not content:
            raise ProviderError("OpenAI devolvió una respuesta vacía.", self.name)
        return content


def _describe_openai_error(exc: Exception) -> str:
    kind = type(exc).__name__
    if kind == "AuthenticationError":
        return "OpenAI rechazó la clave API. Revisa OPENAI_API_KEY."
    if kind == "RateLimitError":
        return "OpenAI indica límite de uso o saldo insuficiente. Inténtalo más tarde."
    if kind in ("APIConnectionError", "APITimeoutError"):
        return "No se pudo conectar con OpenAI (¿hay conexión a Internet?)."
    if kind == "NotFoundError":
        return "OpenAI no encontró el modelo configurado. Revisa 'cloud.model' en settings.yaml."
    return f"Error de OpenAI ({kind})."
