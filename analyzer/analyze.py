"""Автономный анализатор отчётов бота.

Запуск:  python analyze.py "путь_к_папке_с_xlsx"
(этап 1: чтение, проверка и сводка; отчёты появятся на следующих этапах)
"""

import argparse
import sys
from pathlib import Path

from loader import Dataset, LoaderError, discover, load_dataset


def describe(ds: Dataset):
    kind = "СУММАРНЫЙ ФАЙЛ" if ds.is_merged else "Сервер"
    print(f"\n=== {kind}: {ds.title} ===")
    print(f"  Файл:            {ds.path.name}")
    print(f"  Схема данных:    {ds.schema} ({'полная' if ds.full_data else 'урезанная, старый формат'})")
    print(f"  Период:          {ds.period_text or '—'}")
    print(f"  Окно анализа:    {ds.window[0]} — {ds.window[1]} ({ds.window_days} дн.)")
    print(f"  Дни с данными:   {ds.data_start} — {ds.data_end}  |  часовой пояс: {ds.tz or '—'}")
    print(f"  Пользователей:   {len(ds.users)}  |  сообщений: {ds.total_messages:,}".replace(",", " "))
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

    if not loaded:
        return 1
    print(f"\nГотово: прочитано {len(loaded)} из {len(files)} файлов.")
    return 0


if __name__ == "__main__":
    sys.exit(main())