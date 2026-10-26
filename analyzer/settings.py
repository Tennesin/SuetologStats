"""Настройки автономного анализатора. Имена листов и ключей должны совпадать с reports.py бота."""

# Видимые листы отчёта бота
SHEET_SUMMARY = "Сводка"
SHEET_DAILY = "По дням (список)"
SHEET_ANALYTICS = "Аналитика"
SHEET_STAFF = "Администрация"
SHEET_INFO = "Служебное"

# Скрытые служебные листы (схема данных 2)
SHEET_DATA_USERS = "data_users"
SHEET_DATA_CHANNELS = "data_channels"
SHEET_DATA_HEAT = "data_heat"
SHEET_DATA_SERVERS = "data_servers"
SHEET_DATA_PREV = "data_prev"
SHEET_DATA_REPLIES = "data_replies"
SHEET_DATA_MENTIONS = "data_mentions"
SHEET_DATA_REPLY_META = "data_reply_meta"

REQUIRED_SHEETS = [SHEET_SUMMARY, SHEET_DAILY, SHEET_INFO]

# Ключи листа «Служебное», которые могут повторяться
MULTI_KEYS = {"Примечание", "⚠ Внимание"}

KIND_BACK = {"Основатель": "owner", "Админ": "admin"}

MERGED_FILE_PREFIX = "Суммарная"
MERGED_TITLE_PREFIX = "Суммарно по серверам"

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

KIND_RU = {v: k for k, v in KIND_BACK.items()}

# ---------- СКП (этап 3) ----------
SKP_WEIGHTS = {"V": 0.30, "C": 0.25, "R": 0.10, "I": 0.15, "D": 0.10, "P": 0.10}
SKP_NAMES = {
    "V": "Вклад", "C": "Постоянство", "R": "Охват",
    "I": "Взаимодействие", "D": "Зависимость сервера", "P": "Роль",
}
SKP_V_PERCENTILE = 95     # потолок вклада: 95-й перцентиль сообщений по серверу
SKP_C_DAYS_W = 0.6        # внутри C: вес доли активных дней (остальное — доля недель)
SKP_R_MIN_MSGS = 3        # канал засчитывается в охват, если в нём >= N сообщений человека
SKP_R_CAP = 5             # охват 100%, если человек активен в стольких значимых каналах
SKP_SIG_CHANNEL = 0.02    # значимый канал: даёт >= 2% сообщений сервера
SKP_I_PRIOR = 10          # сглаживание доли ответов (как будто 10 сообщений «средних»)
SKP_I_CEIL = 0.35         # доля ответов, при которой взаимодействие считается максимальным
SKP_D_CEIL = 0.5          # доля человека в канале, при которой зависимость максимальна
SKP_ROLE = {"owner": 1.0, "admin": 0.7}
SKP_LEVELS = [(70, "ключевой"), (50, "значимый"), (25, "заметный"), (0, "рядовой")]

# ---------- Риск потери ----------
RISK_WEIGHTS = {"recency": 0.5, "decline": 0.3, "streak": 0.2}
RISK_RECENCY_GAPS = 3     # молчание дольше (1 + N) обычных промежутков = максимум
RISK_DECLINE_RANGE = 0.7  # падение темпа на 70% и больше = максимум
RISK_STREAK_DAYS = 7      # потерянная серия в N дней и больше = максимум
RISK_LEVELS = [(60, "высокий"), (30, "средний"), (0, "низкий")]

# ---------- Отбор для индивидуальных отчётов ----------
SELECT_TOP_N = 20
SELECT_MIN_SKP = 50
MAX_INDIVIDUAL = 60

# ---------- Особая информация о пользователях (пишется вручную) ----------
SPEC_INFO = {
    675694374700580886: "Он ходит в чёрных трусах",
}

# Служебное: те же данные с ID-строками (в анализаторе ID хранятся как строки)
SPEC_INFO_BY_ID = {str(k).strip(): str(v).strip()
                   for k, v in SPEC_INFO.items() if str(v).strip()}