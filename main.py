"""
Разовый сборщик статистики сообщений по истории Discord-сервера.

Запуск:  python main.py
  • На сервере: /stats (точечный анализ одного сервера, с фильтрами).
  • В терминале, где запущен бот: -stats ID1 ID2 ... / -stats all / -servers / -help.
Когда отчёты получены, бота можно остановить (Ctrl+C).

Файлы проекта:
  config.py   — настройки, утилиты, пресеты периодов
  scanner.py  — работа с Discord: каналы, исключения, чтение истории
  reports.py  — Excel и txt отчёты (включая лист «Аналитика»)
  commands.py — слеш-команды и доставка в личные сообщения
  cli.py      — команды терминала

Права бота: «Просмотр каналов» и «Читать историю сообщений».
Требуется: pip install -U discord.py XlsxWriter python-dotenv tzdata
"""

import discord
from discord import app_commands

from cli import start_console
from commands import register_commands
from config import TOKEN, log

class StatBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        register_commands(self)
        await self.tree.sync()
        log.info("Слеш-команды синхронизированы.")
        start_console(self)

    async def on_ready(self):
        log.info("Бот %s запущен. Вызовите /stats на сервере или введите -help в терминале.", self.user)

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "Не задана переменная окружения DISCORD_TOKEN. "
            "Задайте её или создайте файл .env со строкой DISCORD_TOKEN=..."
        )
    StatBot().run(TOKEN, log_handler=None)