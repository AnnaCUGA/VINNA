"""Carga de configuración de VINNA.

Lee ``config/settings.yaml`` y el archivo ``.env`` (si existe). No depende de
python-dotenv: el formato de .env que se admite es sencillo (CLAVE=valor).
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SETTINGS: dict[str, Any] = {
    "ai": {
        "mode": "LOCAL",
        "hybrid": {"prefer": "local", "complex_tasks_to_cloud": True, "complex_min_chars": 400},
        "local": {
            "host": "http://localhost:11434",
            "model": "qwen2.5:1.5b",
            "timeout_seconds": 120,
            "temperature": 0.7,
        },
        "cloud": {"model": "gpt-4o-mini", "timeout_seconds": 60, "temperature": None},
    },
    "privacy": {"send_memories_to_cloud": False},
    "memory": {
        "database": "data/vinna.db",
        "context_messages": 12,
        "context_max_chars": 6000,
        "max_memories_in_prompt": 10,
        "temporary_hours": 24,
    },
    "interface": {"width": 520, "height": 720, "sleep_after_minutes": 5},
    "logging": {"file": "data/vinna.log", "level": "INFO"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_dotenv(path: Path) -> None:
    """Carga variables de un archivo .env sin sobrescribir las ya existentes."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Settings:
    """Configuración ya resuelta (archivo + variables de entorno)."""

    raw: dict[str, Any]
    root: Path = PROJECT_ROOT
    openai_api_key: str | None = field(default=None, repr=False)  # nunca se imprime

    # --- accesos cómodos ---
    @property
    def mode(self) -> str:
        return str(self.raw["ai"]["mode"]).upper()

    @property
    def local(self) -> dict[str, Any]:
        return self.raw["ai"]["local"]

    @property
    def cloud(self) -> dict[str, Any]:
        return self.raw["ai"]["cloud"]

    @property
    def hybrid(self) -> dict[str, Any]:
        return self.raw["ai"]["hybrid"]

    @property
    def memory(self) -> dict[str, Any]:
        return self.raw["memory"]

    @property
    def privacy(self) -> dict[str, Any]:
        return self.raw["privacy"]

    @property
    def interface(self) -> dict[str, Any]:
        return self.raw["interface"]

    @property
    def logging(self) -> dict[str, Any]:
        return self.raw["logging"]

    def resolve_path(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else self.root / path

    @property
    def database_path(self) -> Path:
        return self.resolve_path(self.memory["database"])


def load_settings(config_dir: Path | None = None, root: Path | None = None) -> Settings:
    """Lee settings.yaml y .env. Si falta el archivo, usa valores por defecto."""
    root = root or PROJECT_ROOT
    config_dir = config_dir or root / "config"
    load_dotenv(root / ".env")

    data: dict[str, Any] = {}
    settings_file = config_dir / "settings.yaml"
    if settings_file.is_file():
        with settings_file.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    raw = _deep_merge(DEFAULT_SETTINGS, data)

    # Variables de entorno con prioridad
    if os.environ.get("VINNA_MODE"):
        raw["ai"]["mode"] = os.environ["VINNA_MODE"].upper()
    if os.environ.get("VINNA_OLLAMA_HOST"):
        host = os.environ["VINNA_OLLAMA_HOST"]
        raw["ai"]["local"]["host"] = host if host.startswith("http") else f"http://{host}"
    if os.environ.get("VINNA_OLLAMA_MODEL"):
        raw["ai"]["local"]["model"] = os.environ["VINNA_OLLAMA_MODEL"]
    if os.environ.get("VINNA_DATABASE"):
        raw["memory"]["database"] = os.environ["VINNA_DATABASE"]
    if os.environ.get("VINNA_OPENAI_MODEL"):
        raw["ai"]["cloud"]["model"] = os.environ["VINNA_OPENAI_MODEL"]

    key = os.environ.get("OPENAI_API_KEY", "").strip() or None
    return Settings(raw=raw, root=root, openai_api_key=key)
