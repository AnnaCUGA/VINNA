"""Punto de entrada de VINNA.

Uso (desde la carpeta VINNA-01):
    python -m vinna.main                 # interfaz gráfica
    python -m vinna.main --consola       # modo texto (sin ventana)
    python -m vinna.main --diagnostico   # comprueba Python, Ollama, OpenAI y la base de datos
    python -m vinna.main --modo hibrido  # cambia el modo solo para esta ejecución
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from logging.handlers import RotatingFileHandler

from vinna import __version__
from vinna.brain.cloud_model import OpenAIClient
from vinna.brain.local_model import OllamaClient
from vinna.brain.model_router import Mode, ModelRouter
from vinna.config import Settings, load_settings
from vinna.core.events import ReplyKind
from vinna.core.orchestrator import Orchestrator
from vinna.memory.database import Database
from vinna.personality.character import Personality

log = logging.getLogger("vinna")


def setup_logging(settings: Settings) -> None:
    log_path = settings.resolve_path(settings.logging["file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, str(settings.logging["level"]).upper(), logging.INFO))


def build_router(settings: Settings) -> ModelRouter:
    local = OllamaClient(
        settings.local["host"], settings.local["model"],
        timeout=settings.local["timeout_seconds"], temperature=settings.local.get("temperature"),
    )
    cloud = OpenAIClient(
        settings.openai_api_key, settings.cloud["model"],
        timeout=settings.cloud["timeout_seconds"], temperature=settings.cloud.get("temperature"),
    )
    return ModelRouter(
        local, cloud, Mode.parse(settings.mode),
        hybrid_prefer=settings.hybrid["prefer"],
        complex_tasks_to_cloud=bool(settings.hybrid["complex_tasks_to_cloud"]),
        complex_min_chars=int(settings.hybrid["complex_min_chars"]),
    )


def build_orchestrator(settings: Settings) -> Orchestrator:
    personality = Personality.load(settings.root / "config" / "personality.yaml")
    db = Database(settings.database_path)
    return Orchestrator(settings, personality, db, build_router(settings))


def run_diagnostics(orchestrator: Orchestrator) -> int:
    print(f"VINNA {__version__} · diagnóstico")
    ok_python = sys.version_info >= (3, 11)
    print(f"{'✔' if ok_python else '✘'} Python {sys.version.split()[0]} (se recomienda 3.12)")
    if importlib.util.find_spec("tkinter") is not None:
        print("✔ Tkinter disponible")
    else:
        print("✘ Tkinter no disponible (reinstala Python marcando 'tcl/tk and IDLE')")
    print(f"✔ Base de datos: {orchestrator.db.path}")
    print(f"  Modo: {orchestrator.router.mode.value}")
    for name, (ok, detail) in orchestrator.router.status().items():
        print(f"{'✔' if ok else '✘'} {'Local' if name == 'local' else 'Nube'}: {detail}")
    return 0


def run_console(orchestrator: Orchestrator) -> int:
    name = orchestrator.personality.name
    print(f"{name} (modo consola). Escribe !ayuda para ver comandos, o 'salir' para terminar.")
    while True:
        try:
            text = input("Tú: ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if text.strip().lower() in {"salir", "exit", "quit"}:
            return 0
        reply = orchestrator.handle(text)
        if reply is None:
            continue
        if reply.notice:
            print(f"[aviso] {reply.notice}")
        prefix = {ReplyKind.ASSISTANT: f"{name}: ", ReplyKind.ERROR: "[error] "}.get(reply.kind, "")
        print(prefix + reply.text)


def run_gui(orchestrator: Orchestrator) -> int:
    try:
        import tkinter as tk
    except ImportError:
        print("Tkinter no está disponible. Usa --consola o reinstala Python con Tcl/Tk.")
        return 1
    from vinna.interface.app import VinnaApp

    root = tk.Tk()
    VinnaApp(root, orchestrator)
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vinna", description="VINNA-01, robot de escritorio inteligente")
    parser.add_argument("--consola", action="store_true", help="usar el modo texto en lugar de la ventana")
    parser.add_argument("--diagnostico", action="store_true", help="comprobar el entorno y salir")
    parser.add_argument("--modo", help="local | nube | hibrido (solo para esta ejecución)")
    args = parser.parse_args(argv)

    # En Windows, si la salida se redirige, la codificación puede no admitir ✔/✘.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    settings = load_settings()
    setup_logging(settings)
    if args.modo:
        try:
            settings.raw["ai"]["mode"] = Mode.parse(args.modo).value
        except ValueError as exc:
            parser.error(str(exc))

    log.info("Iniciando VINNA %s en modo %s", __version__, settings.mode)
    orchestrator = build_orchestrator(settings)
    try:
        if args.diagnostico:
            return run_diagnostics(orchestrator)
        if args.consola:
            return run_console(orchestrator)
        return run_gui(orchestrator)
    finally:
        orchestrator.db.close()
        log.info("VINNA cerrado")


if __name__ == "__main__":
    sys.exit(main())
