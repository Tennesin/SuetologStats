"""
Разовый сборщик статистики сообщений по истории Discord-сервера.

Запуск:  python main.py
  • На сервере: /stats (точечный анализ одного сервера, с фильтрами).
  • В терминале, где запущен бот: -stats ID1 ID2 ... / -stats all / -servers / -help.
Когда отчёты получены, бота можно остановить (Ctrl+C).

Файлы проекта:
  config.py       — настройки, утилиты, пресеты периодов
  scanner.py      — работа с Discord: каналы, исключения, чтение истории
  emoji_utils.py  — разбор эмодзи в тексте сообщений
  reports.py      — Excel и txt отчёты (включая лист «Аналитика»)
  commands.py     — слеш-команды и доставка в личные сообщения
  cli.py          — команды терминала

Права бота: «Просмотр каналов» и «Читать историю сообщений».
В Developer Portal должны быть включены Server Members Intent и Message Content Intent.
Требуется: pip install -U discord.py XlsxWriter python-dotenv tzdata emoji
"""

import discord
from discord import app_commands

from cli import start_console
from commands import register_commands
from config import ADMIN_ROLES, IGNORED_CHATS, TOKEN, log

class StatBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        intents.emojis_and_stickers = True   # список эмодзи сервера: отличать «свои» от «внешних»
        intents.message_content = True       # привилегированный: текст сообщений для разбора эмодзи
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        register_commands(self)
        await self.tree.sync()
        log.info("Слеш-команды синхронизированы.")
        start_console(self)

    async def on_ready(self):
        log.info("Бот %s запущен. Вызовите /stats на сервере или введите -help в терминале.", self.user)
        known = {g.id for g in self.guilds}
        for title, table in (("IGNORED_CHATS", IGNORED_CHATS), ("ADMIN_ROLES", ADMIN_ROLES)):
            for gid in table:
                if gid not in known:
                    log.warning("%s: сервер %s не найден среди серверов бота (опечатка в ID?)", title, gid)

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "Не задана переменная окружения DISCORD_TOKEN. "
            "Задайте её или создайте файл .env со строкой DISCORD_TOKEN=..."
        )
    StatBot().run(TOKEN, log_handler=None)