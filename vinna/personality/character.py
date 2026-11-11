"""Personalidad de VINNA.

La personalidad se guarda en ``config/personality.yaml``, separada de las
conversaciones y de los recuerdos. Este módulo la carga y construye el
*prompt de sistema* que se envía a cualquier modelo (local o nube), de modo
que VINNA mantiene la misma identidad sin importar el proveedor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

import yaml

from vinna.memory.pronouns import to_second_person

if TYPE_CHECKING:  # solo para anotaciones; evita dependencias circulares
    from vinna.memory.long_term import Memory

LENGTH_GUIDE = {
    "breve": "Responde de forma breve: una a tres frases.",
    "normal": "Responde con una longitud moderada, sin rodeos.",
    "detallada": "Responde con detalle cuando el tema lo requiera.",
    "adaptable": (
        "Adapta la longitud al contexto: respuestas cortas para charlas y preguntas "
        "simples, más detalladas solo cuando te pidan explicar algo."
    ),
}


MEMORY_INTRO = (
    "Tienes una memoria: el usuario guarda datos sobre sí mismo con el comando !recuerda. "
    "Solo conoces del usuario lo que aparece en la lista de abajo; nunca inventes otros datos."
)


@dataclass
class Personality:
    name: str = "VINNA"
    language: str = "español"
    tone: str = "cercano y tranquilo, con humor ligero ocasional"
    formality: str = "informal pero respetuoso"
    response_length: str = "adaptable"
    traits: list[str] = field(default_factory=lambda: ["curiosa", "amable", "colaborativa"])
    conversational_preferences: list[str] = field(default_factory=list)
    behavior_rules: list[str] = field(
        default_factory=lambda: [
            "No afirmes tener conciencia ni sentimientos humanos.",
            "Si no sabes algo, dilo con honestidad.",
            "Nunca inventes recuerdos.",
        ]
    )

    @classmethod
    def from_dict(cls, data: dict) -> "Personality":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in (data or {}).items() if k in known and v is not None}
        return cls(**clean)

    @classmethod
    def load(cls, path: Path) -> "Personality":
        """Carga la personalidad; si el archivo no existe usa los valores por defecto."""
        if not path.is_file():
            return cls()
        with path.open(encoding="utf-8") as fh:
            return cls.from_dict(yaml.safe_load(fh) or {})

    def build_system_prompt(self, memories: Iterable["Memory"] = ()) -> str:
        """Construye las instrucciones de sistema para el modelo."""
        lines = [
            f"Eres {self.name}, un robot de escritorio inteligente.",
            f"Idioma: responde siempre en {self.language}.",
            f"Personalidad: {', '.join(self.traits)}.",
            f"Tono: {self.tone}. Formalidad: {self.formality}.",
            LENGTH_GUIDE.get(self.response_length, LENGTH_GUIDE["adaptable"]),
        ]
        if self.conversational_preferences:
            lines.append("Preferencias de conversación:")
            lines.extend(f"- {p}" for p in self.conversational_preferences)
        if self.behavior_rules:
            lines.append("Reglas:")
            lines.extend(f"- {r}" for r in self.behavior_rules)

        # Los modelos pequeños usan mejor los recuerdos si se presentan como datos
        # directos sobre el usuario, con una instrucción explícita de cuándo usarlos.
        lines.append("")
        lines.append(MEMORY_INTRO)
        memories = list(memories)
        if memories:
            lines.append("LO QUE SABES DEL USUARIO (te pidió recordarlo; ya está escrito hablándole a él o ella):")
            lines.extend(f"- {to_second_person(m.content)}" for m in memories)
            lines.append(
                "Cuando el usuario pregunte por sí mismo, por sus gustos o por lo que recuerdas, "
                "responde directamente con estos datos. No digas que no tienes memoria."
            )
            lines.append(
                "Estos datos son del USUARIO, no tuyos: al usarlos háblale en segunda persona "
                "(«te gusta», «tu gato», «estás aprendiendo»), nunca en primera persona."
            )
            lines.append(
                "Ejemplo: si sabes «Te gusta el café» y te pregunta «¿qué me gusta tomar?», "
                "responde «¡Te gusta el café!», no «Me gusta el café»."
            )
        else:
            lines.append(
                "Ahora no tienes datos guardados del usuario. Si te pregunta algo sobre sí mismo, "
                "di que no lo recuerdas y que puede pedírtelo con !recuerda."
            )
        return "\n".join(lines)
