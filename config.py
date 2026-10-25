"""
Настройки, мелкие утилиты и пресеты периодов. Про Discord этот модуль ничего не знает.

Переменные окружения (или файл .env рядом со скриптом):
  DISCORD_TOKEN    — токен бота (обязательно)
  TIMEZONE         — часовой пояс для границ дней (по умолчанию Asia/Tashkent)
  ALLOWED_USER_ID  — если задан, команды доступны только пользователю с этим ID
                     (иначе — любому администратору сервера)
  STATS_DIR        — куда сохранять отчёты (по умолчанию папка output рядом с запуском)
  CONCURRENCY      — сколько каналов читать одновременно (по умолчанию 4)
  EXCLUDE_FILE     — путь к JSON-файлу со списком исключений
"""

import calendar
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:  # необязательно: чтение .env, если установлен python-dotenv
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------- Настройки ----------

# Чаты, которые бот пропускает всегда (на всех серверах).
# Строка — ТОЧНОЕ название канала/ветки (без учёта регистра), число — ID канала.
IGNORED_CHATS = [
    1555686019389464668, 1548378402279526510, 1551138756470509598, 1558791241741762560,
    1554857793821872128, 1554900297279868928, 1560031163190353960,
]

ADMIN_ROLES = [
    "Суетологи", "Зам. главы"
]

TOKEN = os.environ.get("DISCORD_TOKEN")
TZ_NAME = os.environ.get("TIMEZONE", "Asia/Tashkent").strip() or "Asia/Tashkent"
STATS_DIR = os.environ.get("STATS_DIR")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0") or 0)
CONCURRENCY = max(1, int(os.environ.get("CONCURRENCY", "4") or 4))
EXCLUDE_FILE = os.environ.get("EXCLUDE_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "excluded_chats.json"
)

DATE_FMT = "%d.%m.%Y"
# Глобальный нижний предел: раньше этой даты не читаем ни один сервер.
MIN_START_DATE = date(2026, 9, 27)
# Официальный день запуска конкретных серверов: {ID сервера: дата}.
GUILD_START_DATES = {
    1548361478103638068: date(2026, 9, 27),   # Суетологи: официальный запуск
    1561089081264316570: date(2026, 10, 18),  # Комитет: официальный запуск
}

NAME_WIDTH = 48
PROGRESS_INTERVAL = 15              # секунд между обновлениями прогресса
UPLOAD_LIMIT = 9 * 1024 * 1024      # с запасом под лимит вложения Discord (10 МБ)
MAX_MATRIX_COLS = 1000              # максимум столбцов в матрице
MAX_LIST_ROWS = 1_000_000           # лимит Excel ~1 048 576 строк на лист

SORT_LABELS = {
    "count": "по количеству сообщений (больше — выше)",
    "name": "по нику (А–Я)",
}
DETAIL_LABELS = {
    "auto": "Авто",
    "days": "По дням",
    "weeks": "По неделям",
    "months": "По месяцам",
}
FORMAT_LABELS = {
    "xlsx": "Excel (xlsx)",
    "txt": "Текст (txt)",
    "both": "Оба файла",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("statbot")


def load_tz(name: str) -> tzinfo:
    if name.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise SystemExit(
            f"Неизвестный часовой пояс TIMEZONE={name!r}. "
            "Пример: Asia/Tashkent. На Windows сначала выполните: pip install tzdata"
        )


TZ = load_tz(TZ_NAME)

# ---------- Вспомогательные функции ----------

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean(text) -> str:
    """Убирает управляющие символы, недопустимые в xlsx."""
    return _CTRL_RE.sub("", str(text))


def parse_date(text: str) -> Optional[date]:
    try:
        return datetime.strptime(text.strip(), DATE_FMT).date()
    except ValueError:
        return None


def fmt_num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} ч {m} мин"
    if m:
        return f"{m} мин {s} с"
    return f"{s} с"


def fit_name(name: str) -> str:
    return name if len(name) <= NAME_WIDTH else name[: NAME_WIDTH - 1] + "…"


def fmt_list(items: list, limit: int = 30) -> str:
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f" … и ещё {len(items) - limit}"


def safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:100] or "server"


def save_local_copy(filename: str, data: bytes, folder: Optional[str] = None) -> str:
    folder = folder or STATS_DIR or "output"
    os.makedirs(folder, exist_ok=True)
    path = os.path.abspath(os.path.join(folder, os.path.basename(filename)))
    with open(path, "wb") as f:
        f.write(data)
    return path


# ---------- Пресеты периодов ----------
# Правило: во всех пресетах учитываются только ЗАВЕРШЁННЫЕ сутки по времени TZ,
# то есть последний день периода — не позже вчерашнего.

PERIOD_PRESETS = {
    "yesterday": "вчера",
    "this-week": "текущая неделя (до вчера)",
    "prev-week": "прошлая неделя",
    "this-month": "текущий месяц (до вчера)",
    "prev-month": "прошлый месяц",
    "this-year": "текущий год (до вчера)",
    "prev-year": "прошлый год",
    "last7d": "последние 7 дней",
    "last30d": "последние 30 дней",
    "last90d": "последние 90 дней",
    "last3m": "последние 3 месяца",
    "last6m": "последние 6 месяцев",
    "last1y": "последний 1 год",
}

_LAST_RE = re.compile(r"^last(\d{1,3})([dwmy])$")
_UNIT_RU = {"d": "дн.", "w": "нед.", "m": "мес.", "y": "г."}


def today_local() -> date:
    """Сегодняшняя дата по часовому поясу TIMEZONE (а не по часам компьютера)."""
    return datetime.now(TZ).date()


def shift_months(d: date, months: int) -> date:
    y, m0 = divmod(d.year * 12 + d.month - 1 + months, 12)
    m = m0 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def normalize_period_key(text: str) -> str:
    key = re.sub(r"[\s_]+", "", str(text).strip().lower())
    return key.replace("last-", "last")


def resolve_period(text: str, today: Optional[date] = None):
    """Возвращает (start, end, key, label); обе даты включительно.
    Бросает ValueError с понятным сообщением."""
    key = normalize_period_key(text)
    today = today or today_local()
    yday = today - timedelta(days=1)
    monday = today - timedelta(days=today.weekday())
    first_month = today.replace(day=1)
    first_year = today.replace(month=1, day=1)

    m = _LAST_RE.match(key)
    if key == "yesterday":
        s, e = yday, yday
    elif key == "this-week":
        s, e = monday, yday
    elif key == "prev-week":
        s, e = monday - timedelta(days=7), monday - timedelta(days=1)
    elif key == "this-month":
        s, e = first_month, yday
    elif key == "prev-month":
        e = first_month - timedelta(days=1)
        s = e.replace(day=1)
    elif key == "this-year":
        s, e = first_year, yday
    elif key == "prev-year":
        e = first_year - timedelta(days=1)
        s = e.replace(month=1, day=1)
    elif m:
        n, unit = int(m.group(1)), m.group(2)
        if n < 1:
            raise ValueError("В пресете lastN число должно быть не меньше 1.")
        e = yday
        try:
            if unit == "d":
                s = yday - timedelta(days=n - 1)
            elif unit == "w":
                s = yday - timedelta(days=n * 7 - 1)
            else:
                s = shift_months(today, -n * (12 if unit == "y" else 1))
        except (ValueError, OverflowError):
            raise ValueError("Слишком большой период.")
    else:
        raise ValueError(
            f"Неизвестный период «{text}». Доступно: {', '.join(PERIOD_PRESETS)} "
            "или lastNd / lastNw / lastNm / lastNy (например last45d)."
        )

    if m:
        label = f"последние {m.group(1)} {_UNIT_RU[m.group(2)]}"
    else:
        label = PERIOD_PRESETS[key]
    if s > e:
        raise ValueError(f"В периоде «{label}» пока нет завершённых суток.")
    return s, e, key, label


def build_period(period: Optional[str], start_text: Optional[str],
                 end_text: Optional[str], compare: bool = False):
    """Единая точка разбора периода для /stats и терминала.
    Возвращает (start, end, key, label). Бросает ValueError.
    Конец периода всегда не позже вчерашнего дня: текущие сутки не завершены."""
    if period and (start_text or end_text):
        raise ValueError("Укажите либо пресет периода, либо даты начала/конца — не одновременно.")
    yday = today_local() - timedelta(days=1)
    if period:
        s, e, key, label = resolve_period(period)
    else:
        s = e = None
        key = label = ""
        if start_text:
            s = parse_date(start_text)
            if s is None:
                raise ValueError("Неверный формат даты начала. Используйте дд.мм.гггг")
        if end_text:
            e = parse_date(end_text)
            if e is None:
                raise ValueError("Неверный формат даты конца. Используйте дд.мм.гггг")
            if e > yday:
                raise ValueError(
                    f"Дата конца не может быть позже вчерашней ({yday.strftime(DATE_FMT)}): "
                    "текущие сутки ещё не завершены."
                )
        else:
            e = yday                    # конец не задан -> последние завершённые сутки
        if s and s > e:
            raise ValueError(
                "Дата начала позже даты конца." if end_text else
                f"Дата начала позже последних завершённых суток ({yday.strftime(DATE_FMT)})."
            )
    if e < MIN_START_DATE:
        raise ValueError(
            f"Период целиком раньше запуска сервера ({MIN_START_DATE.strftime(DATE_FMT)}) "
            "или в нём ещё нет завершённых суток — данных нет."
        )
    if s is None or s < MIN_START_DATE:
        s = MIN_START_DATE          # «с начала истории» и слишком ранние даты подрезаются

    if compare:
        length = (e - s).days + 1
        if s - timedelta(days=length) < MIN_START_DATE:
            raise ValueError(
                "Для сравнения предыдущий период такой же длины начался бы раньше "
                f"{MIN_START_DATE.strftime(DATE_FMT)} — сравнивать не с чем."
            )
    return s, e, key, label