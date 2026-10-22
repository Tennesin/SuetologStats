"""Сбор данных из Discord: поиск каналов, правила исключений, чтение истории."""

import asyncio
import json
import os
import re
import time
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Optional

import discord

from config import (
    ADMIN_ROLES, CONCURRENCY, EXCLUDE_FILE, IGNORED_CHATS, PROGRESS_INTERVAL, TZ,
    fmt_duration, fmt_list, fmt_num, log,
)

# Считаем только обычные сообщения и ответы; системные и сообщения ботов не учитываются.
COUNTED_TYPES = {discord.MessageType.default, discord.MessageType.reply}

running: dict[int, "ScanState"] = {}      # guild_id -> активный сбор
background_tasks: set[asyncio.Task] = set()


def chan_label(ch) -> str:
    if isinstance(ch, discord.Thread) and ch.parent is not None:
        return f"#{ch.parent.name} › {ch.name}"
    return f"#{ch.name}"


# ---------- Параметры, состояние, результат ----------

@dataclass
class ScanParams:
    start_date: Optional[date]
    end_date: Optional[date]
    user: Optional[discord.Member]
    channel: Optional[discord.TextChannel]
    sort_key: str
    detail: str = "auto"
    fmt: str = "xlsx"
    exclude: str = ""
    period_key: str = ""       # ключ пресета ("prev-month"), если задан
    period_label: str = ""     # человекочитаемое название пресета
    compare: bool = False      # сравнить с предыдущим периодом той же длины

    @property
    def prev_range(self) -> Optional[tuple[date, date]]:
        """Предыдущий период той же длины, вплотную перед текущим."""
        if not (self.compare and self.start_date and self.end_date):
            return None
        length = (self.end_date - self.start_date).days + 1
        prev_end = self.start_date - timedelta(days=1)
        return prev_end - timedelta(days=length - 1), prev_end

@dataclass
class StaffMember:
    name: str                  # отображаемый ник
    username: str              # оригинальный логин
    kind: str                  # "owner" или "admin"
    roles: list = field(default_factory=list)   # какие роли из ADMIN_ROLES у человека


@dataclass
class StaffInfo:
    owner_id: Optional[int] = None
    members: dict = field(default_factory=dict)          # uid -> StaffMember
    unmatched_roles: list = field(default_factory=list)  # правила из ADMIN_ROLES без совпадений
    partial: bool = False                                # список участников мог загрузиться не полностью


@dataclass
class ScanResult:
    user_day: dict = field(default_factory=lambda: defaultdict(int))      # (uid, date) -> n
    user_channel: dict = field(default_factory=lambda: defaultdict(int))  # (uid, channel_id) -> n
    heat: dict = field(default_factory=lambda: defaultdict(int))          # (weekday, hour) -> n
    user_heat: dict = field(default_factory=lambda: defaultdict(int))     # (uid, weekday, hour) -> n
    replies: dict = field(default_factory=lambda: defaultdict(int))       # uid -> n
    names: dict = field(default_factory=dict)                             # uid -> ник
    usernames: dict = field(default_factory=dict)                         # uid -> оригинальный ник
    merged: bool = False                                                  # True у суммарного результата
    channel_names: dict = field(default_factory=dict)                     # channel_id -> название
    user_server: dict = field(default_factory=lambda: defaultdict(int))   # (uid, сервер) -> n (только в сумме)
    prev: Optional["ScanResult"] = None                                   # предыдущий период
    staff: Optional["StaffInfo"] = None                                   # администрация сервера
    staff_servers: dict = field(default_factory=dict)                     # сервер -> StaffInfo (только в сумме)

    @property
    def total(self) -> int:
        return sum(self.user_day.values())


class ScanState:
    def __init__(self, title: str = ""):
        self.title = title
        self.started = time.monotonic()
        self.cancelled = False
        self.done = False
        self.total_channels = 0
        self.channels_done = 0
        self.in_progress: dict[int, str] = {}
        self.seen = 0
        self.counted = 0
        self.inactive = 0
        self.skipped: list[str] = []
        self.failed: list[str] = []
        self.excluded: list[str] = []
        self.unused_rules: list[str] = []
        self.notes: list[str] = []

    def elapsed(self) -> str:
        return fmt_duration(time.monotonic() - self.started)

    def progress_text(self) -> str:
        head = f"[{self.title}] " if self.title else ""
        if self.total_channels == 0:
            return f"⏳ {head}Ищу каналы и ветки… (прошло: {self.elapsed()})"
        now = list(self.in_progress.values())
        reading = fmt_list(now, 4) if now else "—"
        return (
            f"⏳ {head}Идёт сбор. Каналов обработано: {self.channels_done}/{self.total_channels}\n"
            f"Сейчас читаю: {reading}\n"
            f"Просмотрено сообщений: {fmt_num(self.seen)} • учтено: {fmt_num(self.counted)} "
            f"• прошло: {self.elapsed()}"
        )


def period_bounds(params: ScanParams):
    """Границы чтения. При сравнении начало сдвигается на начало предыдущего периода."""
    first = params.prev_range[0] if params.prev_range else params.start_date
    start_dt = datetime.combine(first, dtime.min, tzinfo=TZ) if first else None
    end_dt = (
        datetime.combine(params.end_date + timedelta(days=1), dtime.min, tzinfo=TZ)
        if params.end_date else None
    )
    return start_dt, end_dt


# ---------- Правила исключения чатов ----------

def norm_name(text: str) -> str:
    return str(text).strip().lstrip("#").strip().casefold()


def looks_like_id(token: str) -> bool:
    return token.isdigit() and len(token) >= 17


class ExcludeRules:
    """Набор правил: точные названия (без учёта регистра) и ID каналов."""

    def __init__(self):
        self.names: dict[str, str] = {}
        self.ids: dict[int, str] = {}
        self.hit: set[str] = set()

    def add_name(self, text: str):
        n = norm_name(text)
        if n:
            self.names.setdefault(n, str(text).strip())

    def add_id(self, channel_id: int, label: Optional[str] = None):
        self.ids.setdefault(int(channel_id), label or str(channel_id))

    def add_token(self, token):
        if isinstance(token, int):
            self.add_id(token)
            return
        token = str(token).strip()
        if not token:
            return
        if looks_like_id(token):
            self.add_id(int(token))
        else:
            self.add_name(token)

    def matches(self, ch) -> bool:
        if ch.id in self.ids:
            self.hit.add(self.ids[ch.id])
            return True
        n = norm_name(ch.name)
        if n in self.names:
            self.hit.add(self.names[n])
            return True
        return False

    def unused(self) -> list[str]:
        all_labels = set(self.names.values()) | set(self.ids.values())
        return sorted(all_labels - self.hit, key=str.casefold)


def load_store() -> dict:
    try:
        with open(EXCLUDE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        log.exception("Не удалось прочитать %s", EXCLUDE_FILE)
        return {}


def save_store(data: dict):
    tmp = EXCLUDE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, EXCLUDE_FILE)


def build_rules(guild_id: int, extra_text: Optional[str]) -> ExcludeRules:
    rules = ExcludeRules()
    for item in IGNORED_CHATS:
        rules.add_token(item)
    for entry in load_store().get(str(guild_id), []):
        if entry.get("id"):
            rules.add_id(entry["id"], entry.get("name") or str(entry["id"]))
        elif entry.get("name"):
            rules.add_name(entry["name"])
    if extra_text:
        for tok in re.split(r"[,;\n]", extra_text):
            rules.add_token(tok)
    return rules


# ---------- Поиск каналов ----------

async def collect_channels(guild: discord.Guild, params: ScanParams,
                           rules: ExcludeRules, state: ScanState, bot_user_id: int):
    """Каналы/ветки для чтения. Исключённые, недоступные и заведомо пустые
    за период в список не попадают (учитываются в state)."""
    me = guild.me or await guild.fetch_member(bot_user_id)
    only = params.channel
    start_dt, end_dt = period_bounds(params)

    excluded_ids: set[int] = set()
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            continue
        if rules.matches(ch):
            excluded_ids.add(ch.id)
            state.excluded.append(chan_label(ch))
    if only and only.id in excluded_ids:
        excluded_ids.discard(only.id)
        with suppress(ValueError):
            state.excluded.remove(chan_label(only))
        state.notes.append(
            f"Канал {chan_label(only)} указан в фильтре явно, поэтому правило исключения для него не применялось."
        )

    def thread_excluded(t: discord.Thread) -> bool:
        if t.parent_id in excluded_ids:
            return True
        if rules.matches(t):
            state.excluded.append(chan_label(t))
            return True
        return False

    found: dict[int, discord.abc.Messageable] = {}

    for ch in (*guild.text_channels, *guild.voice_channels, *guild.stage_channels):
        if ch.id not in excluded_ids:
            found[ch.id] = ch

    try:
        for t in await guild.active_threads():
            if not thread_excluded(t):
                found[t.id] = t
    except discord.HTTPException as e:
        log.warning("Не удалось получить активные ветки: %s", e)
        state.failed.append(f"Обнаружение активных веток (HTTP {e.status})")

    parents = [only] if only else [*guild.text_channels, *guild.forums]
    for p in parents:
        if p.id in excluded_ids:
            continue
        perms = p.permissions_for(me)
        if not (perms.view_channel and perms.read_message_history):
            continue
        try:
            async for t in p.archived_threads(limit=None):
                if start_dt and t.archive_timestamp and t.archive_timestamp < start_dt:
                    continue   # порядок выдачи API не гарантирован — только пропускаем
                if not thread_excluded(t):
                    found[t.id] = t
        except discord.HTTPException as e:
            log.warning("Не удалось получить публичные архивные ветки %s: %s", chan_label(p), e)
            state.failed.append(f"Публичные архивные ветки {chan_label(p)} (HTTP {e.status})")
        if isinstance(p, discord.TextChannel):
            try:
                async for t in p.archived_threads(private=True, limit=None):
                    if start_dt and t.archive_timestamp and t.archive_timestamp < start_dt:
                        continue
                    if not thread_excluded(t):
                        found[t.id] = t
            except discord.HTTPException as e:
                log.warning("Не удалось получить приватные архивные ветки %s: %s", chan_label(p), e)
                state.failed.append(f"Приватные архивные ветки {chan_label(p)} (HTTP {e.status})")

    if only:
        found = {
            cid: c for cid, c in found.items()
            if cid == only.id or getattr(c, "parent_id", None) == only.id
        }

    readable = []
    for ch in found.values():
        perms = ch.permissions_for(me)
        if not (perms.view_channel and perms.read_message_history):
            state.skipped.append(chan_label(ch))
            continue
        if end_dt and discord.utils.snowflake_time(ch.id) >= end_dt:
            state.inactive += 1     # канал создан уже после конца периода
            continue
        readable.append(ch)

    readable.sort(key=lambda c: c.id)
    state.unused_rules = rules.unused()
    return readable

# ---------- Состав администрации ----------

async def collect_staff(guild: discord.Guild, state: ScanState) -> StaffInfo:
    """Основатель (владелец сервера) + участники с ролями из ADMIN_ROLES."""
    info = StaffInfo(owner_id=guild.owner_id)

    if not guild.chunked:
        try:
            await guild.chunk()
        except Exception as e:
            log.warning("[%s] Не удалось загрузить список участников: %s", guild.name, e)
            state.notes.append("Не удалось полностью загрузить список участников — состав администрации может быть неполным.")
            info.partial = True

    wanted: dict[str, str] = {}      # ключ правила -> как показывать в отчёте
    for item in ADMIN_ROLES:
        if isinstance(item, int) or looks_like_id(str(item)):
            wanted[f"id:{int(item)}"] = str(item)
        elif norm_name(item):
            wanted[f"name:{norm_name(item)}"] = str(item).strip()

    admin_roles: dict[int, discord.Role] = {}
    hit: set[str] = set()
    for role in guild.roles:
        if role.is_default():
            continue
        for key in (f"id:{role.id}", f"name:{norm_name(role.name)}"):
            if key in wanted:
                admin_roles[role.id] = role
                hit.add(key)
    info.unmatched_roles = [label for key, label in wanted.items() if key not in hit]

    for m in guild.members:
        if m.bot:
            continue
        roles = [r.name for r in m.roles if r.id in admin_roles]
        if m.id == guild.owner_id:
            kind = "owner"
        elif roles:
            kind = "admin"
        else:
            continue
        info.members[m.id] = StaffMember(m.display_name, m.name, kind, roles)

    # Владельца может не быть в кэше — докачиваем отдельно.
    if guild.owner_id and guild.owner_id not in info.members:
        try:
            om = await guild.fetch_member(guild.owner_id)
            info.members[om.id] = StaffMember(
                om.display_name, om.name, "owner",
                [r.name for r in om.roles if r.id in admin_roles])
        except discord.HTTPException:
            info.members[guild.owner_id] = StaffMember(str(guild.owner_id), "", "owner", [])

    if guild.member_count and len(guild.members) < guild.member_count:
        info.partial = True
        state.notes.append(
            f"В кэше {len(guild.members)} из {guild.member_count} участников — "
            "состав администрации мог определиться не полностью."
        )
    if info.unmatched_roles:
        state.notes.append(
            "Роли из ADMIN_ROLES не найдены на сервере: " + ", ".join(info.unmatched_roles)
        )
    return info

# ---------- Чтение истории ----------

async def scan_channels(channels, params: ScanParams, state: ScanState) -> ScanResult:
    start_dt, end_dt = period_bounds(params)
    user_id = params.user.id if params.user else None

    main = ScanResult()
    prev: Optional[ScanResult] = None
    if params.prev_range:
        prev = ScanResult()
        prev.names = main.names                    # ники и названия каналов общие
        prev.usernames = main.usernames
        prev.channel_names = main.channel_names
        main.prev = prev

    name_ts: dict[int, datetime] = {}
    sem = asyncio.Semaphore(CONCURRENCY)

    async def scan_one(ch):
        async with sem:
            if state.cancelled:
                return
            label = chan_label(ch)
            state.in_progress[ch.id] = label
            try:
                async for m in ch.history(limit=None, after=start_dt, oldest_first=True):
                    if end_dt and m.created_at >= end_dt:
                        break
                    state.seen += 1
                    if state.cancelled:
                        break
                    author = m.author
                    if author.bot or m.type not in COUNTED_TYPES:
                        continue
                    if user_id and author.id != user_id:
                        continue
                    local = m.created_at.astimezone(TZ)
                    day = local.date()
                    target = prev if (prev is not None and day < params.start_date) else main
                    uid = author.id
                    target.user_day[(uid, day)] += 1
                    target.user_channel[(uid, ch.id)] += 1
                    target.heat[(local.weekday(), local.hour)] += 1
                    target.user_heat[(uid, local.weekday(), local.hour)] += 1
                    if m.type == discord.MessageType.reply:
                        target.replies[uid] += 1
                    main.channel_names.setdefault(ch.id, label)
                    ts = name_ts.get(uid)
                    if ts is None or m.created_at >= ts:
                        name_ts[uid] = m.created_at
                        main.names[uid] = author.display_name
                        main.usernames[uid] = author.name
                    if target is main:
                        state.counted += 1
            except discord.Forbidden:
                state.skipped.append(label)
            except discord.HTTPException as e:
                log.warning("Ошибка чтения %s: %s", label, e)
                state.failed.append(f"{label} (HTTP {e.status})")
            finally:
                state.in_progress.pop(ch.id, None)
                if not state.cancelled:
                    state.channels_done += 1

    tasks = [asyncio.create_task(scan_one(c)) for c in channels]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for t in tasks:
            t.cancel()
        raise
    return main


async def progress_loop(state: ScanState, status_msg: Optional[discord.Message]):
    while True:
        await asyncio.sleep(PROGRESS_INTERVAL)
        text = state.progress_text()
        log.info(text.replace("\n", " | "))
        if status_msg is not None:
            try:
                await status_msg.edit(content=text)
            except discord.HTTPException:
                pass


async def scan_guild(guild: discord.Guild, params: ScanParams, bot_user_id: int,
                     state: ScanState, status_msg: Optional[discord.Message] = None) -> ScanResult:
    """Полный сбор по одному серверу. Регистрацией в `running` управляет вызывающий."""
    progress_task = asyncio.create_task(progress_loop(state, status_msg))
    try:
        rules = build_rules(guild.id, params.exclude)
        channels = await collect_channels(guild, params, rules, state, bot_user_id)
        state.total_channels = len(channels)
        log.info(
            "[%s] к чтению: %d; исключено: %d; без доступа: %d; пропущено как неактивные: %d",
            guild.name, len(channels), len(state.excluded), len(state.skipped), state.inactive,
        )
        staff = await collect_staff(guild, state)
        result = await scan_channels(channels, params, state)
        result.staff = staff
        return result
    finally:
        progress_task.cancel()
        with suppress(asyncio.CancelledError):
            await progress_task


# ---------- Объединение серверов ----------

def _merge_into(dst: ScanResult, src: ScanResult, server: Optional[str]):
    for key, v in src.user_day.items():
        dst.user_day[key] += v
        if server is not None:
            dst.user_server[(key[0], server)] += v
    for key, v in src.user_channel.items():
        dst.user_channel[key] += v
    for key, v in src.heat.items():
        dst.heat[key] += v
    for key, v in src.user_heat.items():
        dst.user_heat[key] += v
    for uid, v in src.replies.items():
        dst.replies[uid] += v
    for uid, nm in src.names.items():
        dst.names.setdefault(uid, nm)          # ник — с первого сервера, где он встретился
    if server is not None:
        for cid, label in src.channel_names.items():
            dst.channel_names[cid] = f"[{server}] {label}"


def merge_results(results):
    """results: список (guild, state, ScanResult). Возвращает (ScanResult, ScanState)."""
    merged = ScanResult()
    merged.merged = True       # в суммарном отчёте ники показываются без оригинального
    total = ScanState()
    have_prev = bool(results) and all(r.prev is not None for _, _, r in results)
    if have_prev:
        merged.prev = ScanResult()
        merged.prev.names = merged.names
        merged.prev.channel_names = merged.channel_names

    used: set[str] = set()
    for g, s, r in results:
        server = g.name if g.name not in used else f"{g.name} ({g.id})"
        used.add(server)
        _merge_into(merged, r, server)
        if r.staff is not None:
            merged.staff_servers[server] = r.staff
        if have_prev:
            _merge_into(merged.prev, r.prev, None)
        total.total_channels += s.total_channels
        total.channels_done += s.channels_done
        total.seen += s.seen
        total.counted += s.counted
        total.inactive += s.inactive
        total.cancelled = total.cancelled or s.cancelled
        for attr in ("skipped", "failed", "excluded", "unused_rules", "notes"):
            getattr(total, attr).extend(f"[{g.name}] {x}" for x in getattr(s, attr))
    return merged, total