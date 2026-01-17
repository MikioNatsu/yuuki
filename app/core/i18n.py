from __future__ import annotations

import re
from typing import Mapping

_SUPPORTED = {"ru", "uz"}

_LANG_RE = re.compile(r"^[a-zA-Z]{1,8}(?:-[a-zA-Z0-9]{1,8})*$")


def infer_locale_from_headers(headers: Mapping[str, str], *, default_locale: str, locale_header: str) -> str:
    explicit = headers.get(locale_header, "") or headers.get(locale_header.lower(), "")
    explicit = explicit.strip().lower()
    if explicit:
        if explicit.startswith("ru"):
            return "ru"
        if explicit.startswith("uz"):
            return "uz"

    accept = headers.get("accept-language", "") or headers.get("Accept-Language", "")
    accept = accept.strip()
    if accept:
        best = _best_match_accept_language(accept)
        if best in _SUPPORTED:
            return best

    return default_locale if default_locale in _SUPPORTED else "ru"


def _best_match_accept_language(value: str) -> str:
    candidates: list[tuple[str, float]] = []
    for part in value.split(","):
        lang_part = part.strip()
        if not lang_part:
            continue
        lang, q = _parse_lang_q(lang_part)
        if not lang:
            continue
        if lang in _SUPPORTED or lang.split("-")[0] in _SUPPORTED:
            candidates.append((lang.split("-")[0], q))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def _parse_lang_q(part: str) -> tuple[str, float]:
    if ";" not in part:
        lang = part.strip()
        if _LANG_RE.match(lang):
            return lang.lower(), 1.0
        return "", 0.0
    lang_raw, params_raw = part.split(";", 1)
    lang = lang_raw.strip()
    if not _LANG_RE.match(lang):
        return "", 0.0
    q = 1.0
    for p in params_raw.split(";"):
        p = p.strip()
        if p.startswith("q="):
            try:
                q = float(p[2:])
            except ValueError:
                q = 0.0
    return lang.lower(), q


_MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "invalid_image": "Неверный файл изображения.",
        "image_too_large": "Файл изображения слишком большой.",
        "unsupported_image_type": "Неподдерживаемый формат изображения.",
        "image_dimensions_exceeded": "Изображение слишком большое по размеру.",
        "request_invalid": "Некорректный запрос.",
        "not_found": "Ресурс не найден.",
        "method_not_allowed": "Метод не поддерживается.",
        "rate_limited": "Слишком много запросов. Попробуйте позже.",
        "service_unavailable": "Сервис временно недоступен. Попробуйте позже.",
        "recognition_unavailable": "Сервис распознавания временно недоступен. Попробуйте позже.",
        "anime_not_found": "Не удалось найти аниме в каталоге.",
        "links_not_found": "Для этого аниме нет доступных официальных ссылок.",
        "llm_unavailable": "Сервис ответа временно недоступен. Попробуйте позже.",
        "internal_error": "Внутренняя ошибка сервиса.",
        "uncertain": "Не удалось уверенно определить аниме. Лучшие совпадения:",
    },
    "uz": {
        "invalid_image": "Rasm fayli noto‘g‘ri.",
        "image_too_large": "Rasm fayli juda katta.",
        "unsupported_image_type": "Rasm formati qo‘llab-quvvatlanmaydi.",
        "image_dimensions_exceeded": "Rasm o‘lchamlari juda katta.",
        "request_invalid": "So‘rov noto‘g‘ri.",
        "not_found": "Resurs topilmadi.",
        "method_not_allowed": "Ushbu metod qo‘llab-quvvatlanmaydi.",
        "rate_limited": "Juda ko‘p so‘rov yuborildi. Keyinroq urinib ko‘ring.",
        "service_unavailable": "Xizmat vaqtincha mavjud emas. Keyinroq urinib ko‘ring.",
        "recognition_unavailable": "Aniqlash xizmati vaqtincha mavjud emas. Keyinroq urinib ko‘ring.",
        "anime_not_found": "Anime katalogda topilmadi.",
        "links_not_found": "Ushbu anime uchun rasmiy havolalar mavjud emas.",
        "llm_unavailable": "Javob xizmati vaqtincha mavjud emas. Keyinroq urinib ko‘ring.",
        "internal_error": "Xizmatda ichki xatolik yuz berdi.",
        "uncertain": "Animeni aniq topib bo‘lmadi. Eng yaxshi mos kelganlari:",
    },
}


def t(locale: str, key: str) -> str:
    lang = locale if locale in _SUPPORTED else "ru"
    return _MESSAGES.get(lang, {}).get(key, _MESSAGES["ru"].get(key, ""))
