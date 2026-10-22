"""Автономный анализатор отчётов бота.

Запуск:  python analyze.py "путь_к_папке_с_xlsx"
(этап 1: чтение, проверка и сводка; отчёты появятся на следующих этапах)
"""

import argparse
import sys
from pathlib import Path

from loader import Dataset, LoaderError, discover, load_dataset
from metrics import server_metrics, user_metrics
from settings import WEEKDAYS

def describe(ds: Dataset):
    kind = "СУММАРНЫЙ ФАЙЛ" if ds.is_merged else "Сервер"
    print(f"\n=== {kind}: {ds.title} ===")
    print(f"  Файл:            {ds.path.name}")
    print(f"  Схема данных:    {ds.schema} ({'полная' if ds.full_data else 'урезанная, старый формат'})")
    print(f"  Период:          {ds.period_text or '—'}")
    print(f"  Окно анализа:    {ds.window[0]} — {ds.window[1]} ({ds.window_days} дн.)")
    print(f"  Дни с данными:   {ds.data_start} — {ds.data_end}  |  часовой пояс: {ds.tz or '—'}")
    print(f"  Пользователей:   {int((ds.users['n'] > 0).sum())}  |  сообщений: {ds.total_messages:,}".replace(",", " "))
    print(f"  Строк по дням:   {len(ds.daily)}  |  по каналам: {len(ds.channels)}  |  по часам: {len(ds.heat)}")
    if ds.is_merged:
        print(f"  Серверов в сумме: {ds.servers['server'].nunique() if len(ds.servers) else '—'}")
    if ds.compare:
        print(f"  Есть предыдущий период: строк {len(ds.prev_daily)}")
    if len(ds.staff):
        print(f"  Администрация:   {len(ds.staff)} чел.")
    if ds.warnings:
        print("  Предупреждения:")
        for w in ds.warnings:
            print(f"    ! {w}")
    else:
        print("  Проверки пройдены без замечаний.")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="Автономный анализатор отчётов бота")
    ap.add_argument("path", help="папка с xlsx-файлами (или один файл)")
    ap.add_argument("--top", type=int, default=10, help="сколько пользователей показать в топе (0 — не показывать)")
    args = ap.parse_args()

    root = Path(args.path).expanduser()
    if not root.exists():
        print(f"Путь не найден: {root}")
        return 1

    files, chosen = discover(root)
    if chosen:
        print(f"В указанной папке нет xlsx; взята самая свежая вложенная: {chosen}")
    if not files:
        print("xlsx-файлы не найдены.")
        return 1

    print(f"Найдено файлов: {len(files)}")
    loaded = []
    for p in files:
        try:
            loaded.append(load_dataset(p))
        except LoaderError as e:
            print(f"\n[пропущен] {p.name}: {e}")

    for ds in loaded:
        describe(ds)
        show_metrics(ds, args.top)

    if not loaded:
        return 1
    print(f"\nГотово: прочитано {len(loaded)} из {len(files)} файлов.")
    return 0


def _pct(x) -> str:
    return "—" if x is None or x != x else f"{x * 100:.1f}%"


def show_metrics(ds: Dataset, top: int):
    sm = server_metrics(ds)
    rel = sm["reliability"]
    print(f"\n  --- МЕТРИКИ (достоверность: {rel['level']}) ---")
    for note in rel["notes"]:
        print(f"    • {note}")
    if sm["empty"]:
        return

    ov = sm["overview"]
    print(f"  Среднее в день: {ov['avg_per_day']:.1f} (медиана {ov['median_per_day']:.0f}); "
          f"пик: {ov['peak_day']} — {ov['peak_messages']}")
    print(f"  DAU: в среднем {ov['avg_dau']:.1f}, максимум {ov['max_dau']}; "
          f"доля пользователей, активных в средний день: {_pct(ov['stickiness'])}")
    print(f"  Сообщений на пользователя: среднее {ov['msgs_per_user_mean']:.1f}, "
          f"медиана {ov['msgs_per_user_median']:.0f}; доля ответов: {_pct(ov['reply_share'])}")

    tr = sm["trend"]
    if tr["available"]:
        print(f"  Тренд: {tr['direction']} (вторая половина к первой: {_pct(tr['change'])}) "
              f"[достоверность: {tr['rel']['level']}]")
    else:
        print(f"  Тренд: не оценивается ({tr['rel']['notes'][0]})")

    d = sm["distribution"]
    print(f"  Неравенство: Джини {d['gini']:.2f}; топ-1 {_pct(d['top1'])}, топ-5 {_pct(d['top5'])}, "
          f"топ-10% ({d['k10']} чел.) {_pct(d['top10pct'])}")
    print(f"  50% сообщений пишут {d['users_for_50']} чел., 80% — {d['users_for_80']} чел.")

    print("  Сегменты (по доле активных дней):")
    for seg, r in sm["segments"].iterrows():
        print(f"    {seg:<14} {int(r['users']):>5} чел. ({_pct(r['user_share'])}), "
              f"сообщений {_pct(r['message_share'])}")

    t = sm["time"]
    if t:
        print(f"  Время: пик {t['peak_hour']:02d}:00, день недели {WEEKDAYS[t['peak_weekday']]}, "
              f"самые активные 3 часа с {t['best3_start']:02d}:00 ({_pct(t['best3_share'])}), "
              f"ночью {_pct(t['night_share'])}, в выходные {_pct(t['weekend_share'])}")

    lc = sm["lifecycle"]
    line = f"  Жизненный цикл: притихло {lc['dormant']} чел. ({_pct(lc['dormant_share'])})"
    if "retention" in lc:
        line += (f"; удержание 1-й → 2-й половины окна {_pct(lc['retention'])}, "
                 f"новых во 2-й половине {lc['new_second_half']}")
    print(line)

    cp = sm["compare"]
    if cp:
        print(f"  К прошлому периоду: сообщения {_pct(cp['messages_change'])}, "
              f"пользователи {_pct(cp['users_change'])}, удержание {_pct(cp['retention'])} "
              f"(новых {cp['new']}, не писавших {cp['lost']})")

    ch = sm["channels"]
    if ch:
        print(f"  Каналы: топ-3 дают {_pct(ch['top3_share'])}; пишут только в одном канале "
              f"{_pct(ch['single_channel_share'])}; в среднем каналов на человека {ch['mean_channels']:.1f}")
    sv = sm["servers"]
    if sv:
        print(f"  Серверы: пишут на нескольких серверах {sv['multi_server_users']} чел.")
    st = sm["staff"]
    if st:
        print(f"  Администрация: {st['people']} чел., {_pct(st['share'])} всех сообщений")

    um = user_metrics(ds)
    if len(um) and top > 0:
        print(f"\n  Топ-{min(top, len(um))} пользователей:")
        for uid, r in um.head(top).iterrows():
            print(f"    {int(r['rank']):>3}. {str(r['name'])[:24]:<24} {int(r['messages']):>6} сообщ., "
                  f"дней {int(r['active_days']):>3}, серия {int(r['longest_streak'])}, "
                  f"тренд: {r['trend']}, достоверность: {r['reliability']}")


if __name__ == "__main__":
    sys.exit(main())