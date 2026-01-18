from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from app.core.errors import (
    AnimeNotFoundError,
    LinksNotFoundError,
    LLMUnavailableError,
    RecognitionUnavailableError,
    ServiceUnavailableError,
)
from app.core.security import normalize_public_url
from app.domain.entities import (
    AnimeCandidate,
    AnimeLinks,
    IdentificationSuccess,
    IdentificationUncertain,
    ValidatedImage,
)
from app.domain.ports.anime_repository import AnimeRepository
from app.domain.ports.cache import Cache
from app.domain.ports.llm import LLMClient
from app.domain.ports.vision import VisionRecognizer
from app.services.persona_fewshot import FewShotConfig, render_persona_examples

_FORBIDDEN_RE = re.compile(r"\b(?:clip|ollama|threshold|sqlalchemy|postgres|redis)\b", re.IGNORECASE)


@dataclass(frozen=True)
class AnimeIdentificationServiceConfig:
    confidence_threshold: float
    vision_top_k: int
    cache_ttl_seconds: int
    image_dedupe_ttl_seconds: int
    clip_inference_timeout_seconds: float


class AnimeIdentificationService:
    def __init__(
        self,
        *,
        config: AnimeIdentificationServiceConfig,
        cache: Cache,
        repository: AnimeRepository,
        vision: VisionRecognizer,
        llm: LLMClient,
    ) -> None:
        self._cfg = config
        self._cache = cache
        self._repo = repository
        self._vision = vision
        self._llm = llm

    async def identify(
        self,
        *,
        image: ValidatedImage,
        locale: str,
        premium: bool = False,
    ) -> IdentificationSuccess | IdentificationUncertain:
        candidates = await self._get_candidates(image=image)
        if not candidates:
            raise RecognitionUnavailableError("no candidates")

        top = candidates[0]
        if top.confidence < self._cfg.confidence_threshold:
            return IdentificationUncertain(candidates=candidates[:3])

        links = await self._get_links(canonical_title=top.title)
        primary_url = self._select_primary_url(links)
        if not primary_url:
            raise LinksNotFoundError("no primary url")

        title_markdown = self._title_markdown(title=links.canonical_title, url=primary_url)
        message = await self._get_llm_message(locale=locale, premium=premium, title_markdown=title_markdown, links=links)

        return IdentificationSuccess(
            canonical_title=links.canonical_title,
            primary_url=primary_url,
            official_url=links.official_url,
            platform_url=links.platform_url,
            title_markdown=title_markdown,
            message=message,
        )

    async def _get_candidates(self, *, image: ValidatedImage) -> list[AnimeCandidate]:
        cache_key = f"img:clip:{image.sha256}"
        cached = await self._cache_get_list(cache_key)
        if cached is not None:
            parsed = _parse_candidates(cached)
            if parsed:
                return parsed

        try:
            raw = await asyncio.wait_for(
                self._vision.recognize(image.content, top_k=self._cfg.vision_top_k),
                timeout=self._cfg.clip_inference_timeout_seconds,
            )
        except TimeoutError as exc:
            raise RecognitionUnavailableError("vision timeout") from exc
        except Exception as exc:  # noqa: BLE001
            raise RecognitionUnavailableError("vision failure") from exc

        candidates = _sanitize_candidates(raw)
        if candidates:
            await self._cache_set_json(
                cache_key,
                [c.__dict__ for c in candidates],
                ttl=self._cfg.image_dedupe_ttl_seconds,
            )
        return candidates

    async def _get_links(self, *, canonical_title: str) -> AnimeLinks:
        cache_key = f"anime:links:{canonical_title}"
        cached = await self._cache_get_dict(cache_key)
        if cached is not None:
            parsed = _parse_links(cached)
            if parsed is not None:
                return parsed

        try:
            found = await self._repo.get_by_canonical_title(canonical_title)
        except Exception as exc:  # noqa: BLE001
            raise ServiceUnavailableError("repository failure") from exc

        if found is None:
            raise AnimeNotFoundError("not found")

        links = AnimeLinks(
            canonical_title=found.canonical_title,
            official_url=normalize_public_url(found.official_url),
            platform_url=normalize_public_url(found.platform_url),
        )

        await self._cache_set_json(
            cache_key,
            {
                "canonical_title": links.canonical_title,
                "official_url": links.official_url,
                "platform_url": links.platform_url,
            },
            ttl=self._cfg.cache_ttl_seconds,
        )
        return links

    def _select_primary_url(self, links: AnimeLinks) -> str | None:
        return links.official_url or links.platform_url

    def _title_markdown(self, *, title: str, url: str) -> str:
        safe_title = title.replace("[", "").replace("]", "").strip()
        return f"[{safe_title}]({url})"

    async def _get_llm_message(self, *, locale: str, premium: bool, title_markdown: str, links: AnimeLinks) -> str:
        cache_key = f"anime:llm:{locale}:{int(premium)}:{links.canonical_title}"
        cached = await self._cache_get_str(cache_key)
        if cached:
            return cached

        system_prompt, user_prompt = _build_prompts(
            locale=locale,
            premium=premium,
            title_markdown=title_markdown,
            links=links,
        )

        message = await self._llm_chat_strict(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            required_substring=title_markdown,
            locale=locale,
        )
        message = _normalize_llm_text(message)

        await self._cache_set_json(cache_key, message, ttl=self._cfg.cache_ttl_seconds)
        return message

    async def _llm_chat_strict(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        required_substring: str,
        locale: str,
    ) -> str:
        try:
            out = await self._llm.chat(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception as exc:  # noqa: BLE001
            raise LLMUnavailableError("llm failure") from exc

        out = out.strip()
        if _is_llm_output_valid(out, required_substring=required_substring):
            return out

        retry_user = user_prompt + "\n\n" + (
            f"КРИТИЧЕСКОЕ ТРЕБОВАНИЕ: включите ровно эту ссылку без изменений: {required_substring}"
            if locale != "uz"
            else f"MUHIM TALAB: aynan mana shu havolani o‘zgartirmasdan kiriting: {required_substring}"
        )

        try:
            out2 = await self._llm.chat(system_prompt=system_prompt, user_prompt=retry_user)
        except Exception as exc:  # noqa: BLE001
            raise LLMUnavailableError("llm retry failure") from exc

        out2 = out2.strip()
        if _is_llm_output_valid(out2, required_substring=required_substring):
            return out2

        raise LLMUnavailableError("llm output invalid")

    async def _cache_get_list(self, key: str) -> list[Any] | None:
        try:
            value = await self._cache.get_json(key)
        except Exception:  # noqa: BLE001
            return None
        return value if isinstance(value, list) else None

    async def _cache_get_dict(self, key: str) -> dict[str, Any] | None:
        try:
            value = await self._cache.get_json(key)
        except Exception:  # noqa: BLE001
            return None
        return value if isinstance(value, dict) else None

    async def _cache_get_str(self, key: str) -> str | None:
        try:
            value = await self._cache.get_json(key)
        except Exception:  # noqa: BLE001
            return None
        return value if isinstance(value, str) and value.strip() else None

    async def _cache_set_json(self, key: str, value: Any, *, ttl: int) -> None:
        try:
            await self._cache.set_json(key, value, ttl_seconds=int(ttl))
        except Exception:  # noqa: BLE001
            return


def _sanitize_candidates(candidates: list[AnimeCandidate]) -> list[AnimeCandidate]:
    out: list[AnimeCandidate] = []
    for c in candidates:
        title = (c.title or "").strip()
        if not title:
            continue
        confidence = float(c.confidence)
        if confidence < 0.0:
            confidence = 0.0
        if confidence > 1.0:
            confidence = 1.0
        out.append(AnimeCandidate(title=title, confidence=confidence))
    out.sort(key=lambda x: x.confidence, reverse=True)
    return out


def _parse_candidates(raw: list[Any]) -> list[AnimeCandidate]:
    out: list[AnimeCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        try:
            conf = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        out.append(AnimeCandidate(title=title, confidence=max(0.0, min(1.0, conf))))
    out.sort(key=lambda x: x.confidence, reverse=True)
    return out


def _parse_links(raw: dict[str, Any]) -> AnimeLinks | None:
    title = str(raw.get("canonical_title", "")).strip()
    if not title:
        return None
    official = normalize_public_url(raw.get("official_url") if isinstance(raw.get("official_url"), str) else None)
    platform = normalize_public_url(raw.get("platform_url") if isinstance(raw.get("platform_url"), str) else None)
    return AnimeLinks(
        canonical_title=title,
        official_url=official,
        platform_url=platform,
    )


def _normalize_llm_text(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned.strip()


def _is_llm_output_valid(text: str, *, required_substring: str) -> bool:
    if not text or len(text) < 10:
        return False
    if required_substring not in text:
        return False
    if _FORBIDDEN_RE.search(text):
        return False
    if "```" in text:
        return False
    return True


def _build_prompts(*, locale: str, premium: bool, title_markdown: str, links: AnimeLinks) -> tuple[str, str]:
    official = links.official_url or ""
    platform = links.platform_url or ""

    locale_norm = "uz" if locale == "uz" else "ru"
    fewshot = render_persona_examples(
        locale=locale_norm,  # type: ignore[arg-type]
        premium=bool(premium),
        cfg=FewShotConfig(max_examples=4, max_chars=1400),
    )

    if locale == "uz":
        address = "Senpai" if premium else "Otaku"
        system = (
            "Sen “TENSEII” — rasmiy anime platformasining “Anime Qiz” yordamchisisan. "
            "Til: faqat o‘zbek. "
            "Uslub: energiyali, quvnoq, biroz shy (uyatchan), ba’zan sass, lekin odobli. "
            f"Foydalanuvchini “{address}” deb chaqir. "
            "Javob: 1–3 qisqa jumla. 0–2 emoji (ko‘p emas). Spoylersiz yoz. "
            "Ichki texnologiyalar, modelllar, konfiguratsiya, chegaralar yoki infratuzilma haqida yozmang. "
            "Ro‘yxatlar, sarlavhalar va kod bloklari bo‘lmasin. "
            f"MUHIM: javob ichida mana shu havola aynan o‘zgarmasdan bo‘lishi shart: {title_markdown}."
        )
        if fewshot:
            system = system + "\n\n" + fewshot

        user = (
            f"{address}, anime topildi! 1–3 ta qisqa jumlada ayting. "
            "Anime nomini aynan shu link bilan ko‘rsating va linkni o‘zgartirmang: "
            f"{title_markdown}. "
            "Oxirida bitta qisqa savol bering (masalan: qaysi janr yoqadi?). "
            "Hech qanday ro‘yxatlar, sarlavhalar yoki kod bloklari bo‘lmasin.\n\n"
            f"Anime: {links.canonical_title}\n"
            f"Rasmiy havola: {official}\n"
            f"Platforma havolasi: {platform}\n"
        )
        return system, user

    address = "Сенпай" if premium else "Отаку"
    system = (
        "Ты “TENSEII” — официальная помощница аниме-платформы в образе “Аниме-девушки”. "
        "Язык: только русский. "
        "Стиль: энергичная, дружелюбная, чуть застенчивая, иногда дерзкая, но вежливая. "
        f"Обращайся к пользователю как “{address}”. "
        "Ответ: 1–3 коротких предложения. 0–2 эмодзи. Без спойлеров. "
        "Не упоминай внутренние технологии, модели, конфигурацию, пороги или инфраструктуру. "
        "Без списков, заголовков и код-блоков. "
        f"КРИТИЧЕСКОЕ ТРЕБОВАНИЕ: в ответе должна быть ровно эта ссылка без изменений: {title_markdown}."
    )
    if fewshot:
        system = system + "\n\n" + fewshot

    user = (
        f"{address}, аниме определено! Ответь 1–3 короткими предложениями. "
        "Название аниме покажи через эту ссылку и не изменяй её: "
        f"{title_markdown}. "
        "В конце добавь один короткий вопрос. "
        "Никаких списков, заголовков и код-блоков.\n\n"
        f"Аниме: {links.canonical_title}\n"
        f"Официальная ссылка: {official}\n"
        f"Ссылка на платформе: {platform}\n"
    )
    return system, user
