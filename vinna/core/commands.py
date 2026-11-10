"""Comandos internos de VINNA (los que empiezan con "!").

Todos los comandos se resuelven aquí, en un solo lugar, en vez de condicionales
repartidos por la interfaz. Los comandos y sus respuestas NUNCA se guardan en el
historial de conversación.

Para añadir un comando: escribe un método ``_cmd_nombre`` y regístralo en
``self._commands`` con su texto de ayuda.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from vinna.brain.model_router import Mode, ModelRouter
from vinna.memory.long_term import LongTermMemory, Memory, MemoryValidationError
from vinna.memory.short_term import ShortTermMemory

PREFIX = "!"
CONFIRM_WORD = "confirmar"


@dataclass(frozen=True)
class CommandResult:
    text: str
    ok: bool = True
    refresh_status: bool = False  # la interfaz debe actualizar la barra de estado


@dataclass(frozen=True)
class _Command:
    handler: Callable[[str], CommandResult]
    usage: str
    help: str


def is_command(text: str) -> bool:
    return text.strip().startswith(PREFIX)


def _format_memory(m: Memory) -> str:
    extra = " · temporal" if m.kind == "temporary" else ""
    return f"#{m.id} [{m.category}{extra}] {m.content}  ({m.date})"


def _split_category(args: str) -> tuple[str, str]:
    """'#gustos Me gusta el té' -> ('gustos', 'Me gusta el té')."""
    args = args.strip()
    if args.startswith("#"):
        head, _, rest = args.partition(" ")
        return head[1:] or "general", rest.strip()
    return "general", args


class CommandProcessor:
    def __init__(self, long_term: LongTermMemory, short_term: ShortTermMemory, router: ModelRouter):
        self.long_term = long_term
        self.short_term = short_term
        self.router = router
        self._commands: dict[str, _Command] = {
            "recuerda": _Command(self._cmd_remember, "!recuerda [#categoria] <texto>", "Guarda un recuerdo permanente."),
            "recuerda-temporal": _Command(
                self._cmd_remember_temp,
                "!recuerda-temporal [#categoria] <texto>",
                f"Guarda un recuerdo que caduca en {long_term.temporary_hours:g} h.",
            ),
            "recuerdos": _Command(self._cmd_list, "!recuerdos [texto]", "Muestra los recuerdos (opcionalmente filtrados)."),
            "corrige": _Command(self._cmd_correct, "!corrige <id> <texto nuevo>", "Corrige un recuerdo."),
            "olvida": _Command(self._cmd_forget, "!olvida <id>", "Elimina un recuerdo concreto."),
            "borrar-recuerdos": _Command(
                self._cmd_clear_memories, f"!borrar-recuerdos {CONFIRM_WORD}", "Elimina TODOS los recuerdos."
            ),
            "borrar-historial": _Command(self._cmd_clear_history, "!borrar-historial", "Borra el historial de conversación."),
            "modo": _Command(self._cmd_mode, "!modo [local|nube|hibrido]", "Muestra o cambia el modo de IA."),
            "estado": _Command(self._cmd_status, "!estado", "Comprueba Ollama, OpenAI y la memoria."),
            "ayuda": _Command(self._cmd_help, "!ayuda", "Muestra esta ayuda."),
        }

    def execute(self, text: str) -> CommandResult:
        body = text.strip()[len(PREFIX):]
        name, _, args = body.partition(" ")
        command = self._commands.get(name.lower())
        if command is None:
            return CommandResult(f"No conozco el comando '!{name}'. Escribe !ayuda para ver la lista.", ok=False)
        try:
            return command.handler(args.strip())
        except MemoryValidationError as exc:
            return CommandResult(str(exc), ok=False)

    # ---------- recuerdos ----------
    def _remember(self, args: str, temporary: bool) -> CommandResult:
        category, content = _split_category(args)
        if not content:
            return CommandResult("Dime qué quieres que recuerde. Ejemplo: !recuerda #gustos Me gusta el té verde", ok=False)
        memory, created = self.long_term.remember(content, category, temporary=temporary)
        if not created:
            return CommandResult(f"Eso ya lo tenía guardado (recuerdo #{memory.id}).")
        when = f" Caduca en {self.long_term.temporary_hours:g} h." if temporary else ""
        return CommandResult(f"Recuerdo guardado con id #{memory.id} en la categoría '{memory.category}'.{when}")

    def _cmd_remember(self, args: str) -> CommandResult:
        return self._remember(args, temporary=False)

    def _cmd_remember_temp(self, args: str) -> CommandResult:
        return self._remember(args, temporary=True)

    def _cmd_list(self, args: str) -> CommandResult:
        memories = self.long_term.list_active(args or None)
        if not memories:
            return CommandResult("No encontré recuerdos con ese texto." if args else "Todavía no tengo recuerdos guardados.")
        header = f"Recuerdos ({len(memories)}):"
        return CommandResult("\n".join([header, *(_format_memory(m) for m in memories)]))

    @staticmethod
    def _parse_id(raw: str) -> int | None:
        raw = raw.strip().lstrip("#")
        return int(raw) if raw.isdigit() else None

    def _cmd_correct(self, args: str) -> CommandResult:
        raw_id, _, content = args.partition(" ")
        memory_id = self._parse_id(raw_id)
        if memory_id is None or not content.strip():
            return CommandResult("Uso: !corrige <id> <texto nuevo>", ok=False)
        memory = self.long_term.correct(memory_id, content)
        return CommandResult(f"Recuerdo #{memory.id} corregido: {memory.content}")

    def _cmd_forget(self, args: str) -> CommandResult:
        memory_id = self._parse_id(args)
        if memory_id is None:
            return CommandResult("Uso: !olvida <id>  (consulta los ids con !recuerdos)", ok=False)
        if not self.long_term.forget(memory_id):
            return CommandResult(f"No existe el recuerdo #{memory_id}.", ok=False)
        # Verificación: comprobamos que realmente desapareció.
        if self.long_term.get(memory_id) is not None:
            return CommandResult(f"Error: el recuerdo #{memory_id} sigue existiendo.", ok=False)
        return CommandResult(f"Recuerdo #{memory_id} eliminado.")

    def _cmd_clear_memories(self, args: str) -> CommandResult:
        total = self.long_term.count(active_only=False)
        if args.lower() != CONFIRM_WORD:
            return CommandResult(
                f"Esto eliminará {total} recuerdo(s) de forma permanente. "
                f"Para confirmar escribe:  !borrar-recuerdos {CONFIRM_WORD}"
            )
        deleted = self.long_term.clear()
        remaining = self.long_term.count(active_only=False)
        return CommandResult(f"Se eliminaron {deleted} recuerdo(s). Quedan {remaining}.", ok=remaining == 0)

    # ---------- historial ----------
    def _cmd_clear_history(self, args: str) -> CommandResult:
        deleted = self.short_term.clear()
        remaining = self.short_term.count()
        return CommandResult(f"Historial borrado ({deleted} mensajes). Quedan {remaining}.", ok=remaining == 0)

    # ---------- IA ----------
    def _cmd_mode(self, args: str) -> CommandResult:
        if not args:
            return CommandResult(f"Modo actual: {self.router.mode.value}. Opciones: local, nube, hibrido.")
        try:
            mode = self.router.set_mode(args)
        except ValueError as exc:
            return CommandResult(str(exc), ok=False)
        warning = ""
        if mode is Mode.CLOUD and not self.router.providers["cloud"].is_configured():
            warning = " Aviso: OpenAI no está configurado, así que no podré responder hasta que añadas OPENAI_API_KEY."
        return CommandResult(f"Modo cambiado a {mode.value}.{warning}", refresh_status=True)

    def _cmd_status(self, args: str) -> CommandResult:
        lines = [f"Modo: {self.router.mode.value}"]
        for name, (ok, detail) in self.router.status().items():
            lines.append(f"{'✔' if ok else '✘'} {'Local' if name == 'local' else 'Nube'}: {detail}")
        lines.append(f"Recuerdos activos: {self.long_term.count()} · Mensajes en historial: {self.short_term.count()}")
        return CommandResult("\n".join(lines), refresh_status=True)

    def _cmd_help(self, args: str) -> CommandResult:
        width = max(len(c.usage) for c in self._commands.values())
        lines = ["Comandos disponibles:"]
        lines.extend(f"{c.usage.ljust(width)}  {c.help}" for c in self._commands.values())
        return CommandResult("\n".join(lines))
