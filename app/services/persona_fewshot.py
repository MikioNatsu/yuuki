from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

Locale = Literal["uz", "ru"]
DatasetLanguage = Literal["uzbek", "russian"]


class PersonaExample(BaseModel):
    instruction: str = Field(min_length=1, max_length=300)
    input: str = Field(min_length=1, max_length=500)
    language: DatasetLanguage
    premium: bool
    output: str = Field(min_length=1, max_length=800)


@dataclass(frozen=True)
class FewShotConfig:
    max_examples: int = 4
    max_chars: int = 1400


def _dataset_language(locale: Locale) -> DatasetLanguage:
    return "uzbek" if locale == "uz" else "russian"


@lru_cache(maxsize=1)
def _load_dataset() -> tuple[PersonaExample, ...]:
    try:
        data_text = resources.files("app.resources").joinpath("persona_dataset.json").read_text(encoding="utf-8")
    except Exception:
        return tuple()

    try:
        raw = json.loads(data_text)
    except Exception:
        return tuple()

    if not isinstance(raw, list):
        return tuple()

    out: list[PersonaExample] = []
    for item in raw:
        try:
            ex = PersonaExample.model_validate(item)
        except ValidationError:
            continue
        out.append(ex)

    return tuple(out)


def render_persona_examples(*, locale: Locale, premium: bool, cfg: FewShotConfig | None = None) -> str:
    config = cfg or FewShotConfig()
    ds = _load_dataset()
    if not ds:
        return ""

    lang = _dataset_language(locale)

    exact: list[PersonaExample] = [x for x in ds if x.language == lang and x.premium is premium]
    fallback: list[PersonaExample] = [x for x in ds if x.language == lang and x.premium is not premium]

    selected: list[PersonaExample] = []
    for x in exact:
        selected.append(x)
        if len(selected) >= config.max_examples:
            break

    if len(selected) < config.max_examples:
        for x in fallback:
            selected.append(x)
            if len(selected) >= config.max_examples:
                break

    if not selected:
        return ""

    header = (
        "USLUB NAMUNALARI (faqat uslub uchun, fakt emas):\n"
        if locale == "uz"
        else "ПРИМЕРЫ СТИЛЯ (только стиль, не факты):\n"
    )

    parts: list[str] = [header]
    used = 0
    for ex in selected:
        block = f"User: {ex.input}\nAssistant: {ex.output}\n"
        if used + len(block) > config.max_chars:
            break
        parts.append(block)
        used += len(block)

    return "\n".join(p.strip("\n") for p in parts if p).strip()
