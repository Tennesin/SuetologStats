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

REQUIRED_SHEETS = [SHEET_SUMMARY, SHEET_DAILY, SHEET_INFO]

# Ключи листа «Служебное», которые могут повторяться
MULTI_KEYS = {"Примечание", "⚠ Внимание"}

KIND_BACK = {"Основатель": "owner", "Админ": "admin"}

MERGED_FILE_PREFIX = "Суммарная"
MERGED_TITLE_PREFIX = "Суммарно по серверам"

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]