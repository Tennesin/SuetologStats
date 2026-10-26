"""Разбор эмодзи в тексте сообщения. Про Discord и файлы этот модуль ничего не знает."""

import re

import emoji as _lib

# <:имя:123> и анимированные <a:имя:123>
CUSTOM_RE = re.compile(r"<(a?):(\w{1,32}):(\d{15,25})>")

# Быстрая отсечка: эмодзи всегда содержит символ с кодом >= U+203C (или это кастомный <:..:>).
# Обычный русский/английский текст сюда не попадает и тяжёлую библиотеку не вызывает.
_MAYBE = re.compile("[\u203c-\U0010ffff]|<a?:")

_SKIN = re.compile("[\U0001F3FB-\U0001F3FF]")      # оттенки кожи
_VS = re.compile("[\uFE0E\uFE0F]")                  # селекторы вариации
_GENDER = re.compile("\u200d[\u2640\u2642]$")       # 🤷‍♂️ / 🤷‍♀️ -> 🤷  (не нужно — удалите эту строку и её вызов)
_JUNK = re.compile("[\\s\u200d\uFE0E\uFE0F]")       # остатки, которые не считаются текстом


def normalize_unicode(ch: str) -> str:
    """Сливает вариации одного эмодзи: без оттенков кожи, без FE0F, без гендерного суффикса."""
    s = _SKIN.sub("", ch)
    s = _VS.sub("", s)
    return _GENDER.sub("", s)


def parse_emoji(text: str):
    """Возвращает (found, only).
    found — список (ключ, имя, анимированный, id_кастомного); по записи на каждое вхождение.
        Ключ: "c:<id>" для кастомного, "u:<символ>" для обычного Unicode.
        Для Unicode имя пустое, id равен 0.
    only — True, если в сообщении кроме эмодзи нет ничего (кроме пробелов)."""
    if not text or not _MAYBE.search(text):
        return [], False

    found = [(f"c:{m.group(3)}", m.group(2), bool(m.group(1)), int(m.group(3)))
             for m in CUSTOM_RE.finditer(text)]
    rest = CUSTOM_RE.sub(" ", text)

    lst = _lib.emoji_list(rest)
    pos, parts = 0, []
    for it in lst:
        found.append(("u:" + normalize_unicode(it["emoji"]), "", False, 0))
        parts.append(rest[pos:it["match_start"]])
        pos = it["match_end"]
    parts.append(rest[pos:])

    if not found:
        return [], False
    return found, _JUNK.sub("", "".join(parts)) == ""