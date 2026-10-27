"""Этап 5: раздел «Реакции» для HTML-отчётов. Показывается только если в файле есть данные о реакциях."""

from emoji_tools import info_map
from metrics import REACTION_MIN_MSGS, names_map
from report_emoji import STYLE, emoji_html
from report_html import Raw, _bad, _link, card, esc, h2, num, pct, table

def _givers_of(r) -> object:
    return int(r["givers"]) if ("givers" in r.index and not _bad(r["givers"])) else "—"

def _emoji_rows(df, info, imgs, n: int, full: bool) -> list:
    if df is None or df.empty:
        return []
    top = df.head(n)
    mx = float(top["uses"].max()) or 1.0
    rows = []
    for i, (key, r) in enumerate(top.iterrows(), start=1):
        w = 120 * float(r["uses"]) / mx
        row = [i, emoji_html(key, info, imgs), int(r["uses"]), pct(r["share"]),
               Raw(f'<span class="bar" style="width:{w:.0f}px"></span>'),
               int(r["users"]), int(r["text_uses"])]
        if full:
            row.append(_givers_of(r))
        rows.append(row)
    return rows

def _emoji_table(df, info, imgs, n: int, full: bool) -> str:
    head = ["№", "Эмодзи", "Реакций", "Доля", "", "Получателей", "В тексте сообщений"]
    nums = [0, 2, 3, 5, 6]
    if full:
        head.append("Поставили (людей)")
        nums.append(7)
    return table(head, _emoji_rows(df, info, imgs, n, full), num_cols=tuple(nums))

def _people_rows(df, info, imgs, linked) -> list:
    rows = []
    for i, (uid, r) in enumerate(df.iterrows(), start=1):
        fav = emoji_html(r["rx_top_key"], info, imgs) if r["rx_top_key"] else "—"
        rows.append([i, _link(uid, r["name"], linked), int(r["messages"]), int(r["rx_recv"]),
                     pct(r["rx_msg_share"]), f"{r['rx_per_msg']:.2f}", fav, r["reliability"]])
    return rows

_PEOPLE_HEAD = ["№", "Пользователь", "Сообщений", "Получено реакций", "Доля сообщений с реакциями",
                "Реакций на сообщение", "Любимая полученная", "Достоверность"]
_PEOPLE_NUM = (0, 2, 3, 4, 5)

def build_server_reactions_html(ds, rx, um, linked, imgs) -> str:
    if not rx or not rx.get("available"):
        return ""
    info = info_map(ds.emoji_info)
    full = rx["full"]
    b = [STYLE, h2("Реакции", rx["rel"])]
    mode = "полный (известно, кто ставил)" if full else "счётчики (без списка людей)"
    b.append(f'<p class="muted">Режим сбора: {esc(mode)}. Реакции — снимок на момент сбора, '
             "они привязаны ко дню сообщения.</p>")

    cards = [
        card("Реакций получено", num(rx["uses"]), f"разных эмодзи: {rx['distinct']}"),
        card("Сообщений с реакциями", num(rx["msgs_with"]), f"{pct(rx['msgs_share'])} от всех"),
        card("Реакций на сообщение", num(rx["per_msg"], 2)),
        card("Людей получили реакции", num(rx["users_with"]), pct(rx["users_with_share"])),
    ]
    if full:
        cards.append(card("Людей ставили реакции", num(rx["givers_total"])))
    b.append('<div class="cards">' + "".join(cards) + "</div>")

    if rx["empty"]:
        b.append('<div class="box">Реакций под сообщениями за период не найдено.</div>')
    else:
        b.append("<h3>Из чего состоят реакции</h3>")
        b.append(table(["Тип", "Разных", "Реакций", "Доля"],
                       [[name, d, num(u), pct(s)] for name, d, u, s in rx["categories"]],
                       num_cols=(1, 2, 3)))

        b.append("<h3>Рейтинг эмодзи в реакциях</h3>")
        b.append('<p class="muted">Колонка «В тексте сообщений» показывает, сколько раз этот же '
                 "эмодзи написали словами в сообщениях: видно, какие эмодзи чаще ставят, чем пишут.</p>")
        b.append(_emoji_table(rx["top"], info, imgs, 15, full))

        if rx["top_own"] is not None and len(rx["top_own"]):
            b.append("<h3>Свои кастомные эмодзи в реакциях</h3>")
            b.append(_emoji_table(rx["top_own"], info, imgs, 10, full))
        if rx["top_ext"] is not None and len(rx["top_ext"]):
            b.append("<h3>Внешние кастомные эмодзи в реакциях (внешний)</h3>")
            b.append(_emoji_table(rx["top_ext"], info, imgs, 10, full))

        tr = rx["top_received"]
        if tr is not None and len(tr):
            b.append("<h3>Больше всего получили реакций</h3>")
            b.append(table(_PEOPLE_HEAD, _people_rows(tr, info, imgs, linked), num_cols=_PEOPLE_NUM))

        rate = rx["top_rate"]
        if rate is not None and len(rate):
            b.append("<h3>Больше реакций на одно сообщение</h3>")
            b.append(f'<p class="muted">Только люди, у которых не меньше {REACTION_MIN_MSGS} сообщений.</p>')
            b.append(table(_PEOPLE_HEAD, _people_rows(rate, info, imgs, linked), num_cols=_PEOPLE_NUM))

        gv = rx.get("givers")
        if gv is not None and len(gv):
            b.append("<h3>Кто чаще всех ставит реакции</h3>")
            rows = [[i, _link(uid, r["name"], linked), int(r["given"]), int(r["distinct"]), int(r["targets"])]
                    for i, (uid, r) in enumerate(gv.iterrows(), start=1)]
            b.append(table(["№", "Пользователь", "Поставлено", "Разных эмодзи", "Кому (людей)"],
                           rows, num_cols=(0, 2, 3, 4)))

        pairs = rx.get("pairs")
        if pairs is not None and len(pairs):
            b.append("<h3>Кто кому чаще ставит реакции</h3>")
            rows = [[i, r["src_name"], r["dst_name"], int(r["n"])]
                    for i, (_k, r) in enumerate(pairs.iterrows(), start=1)]
            b.append(table(["№", "Кто поставил", "Кому", "Реакций"], rows, num_cols=(0, 3)))

    b.append('<div class="box muted"><b>Как читать:</b><ul>'
             + "".join(f"<li>{esc(x)}</li>" for x in rx["rel"]["notes"]) + "</ul></div>")
    return "".join(b)

def build_user_reactions_html(ds, uid, um, rx, imgs) -> str:
    if not rx or not rx.get("available") or uid not in um.index:
        return ""
    r = um.loc[uid]
    if _bad(r["rx_recv"]):
        return ""
    info = info_map(ds.emoji_info)
    full = rx["full"]
    recv = int(r["rx_recv"])

    b = [STYLE, h2("Реакции")]
    cards = [
        card("Реакций получено", num(recv), f"разных: {num(r['rx_distinct'])}"),
        card("Сообщений с реакциями", num(r["rx_msgs"]), pct(r["rx_msg_share"])),
        card("Реакций на сообщение", num(r["rx_per_msg"], 2)),
    ]
    if full:
        cards.append(card("Реакций поставлено", num(r["rx_given"]), f"разных: {num(r['rx_given_distinct'])}"))
        cards.append(card("Ставил(а) реакции", num(r["rx_given_targets"]), "людям"))
    b.append('<div class="cards">' + "".join(cards) + "</div>")

    mine = ds.reaction_recv[ds.reaction_recv["uid"] == uid].sort_values("n", ascending=False, kind="stable")
    if recv == 0 or mine.empty:
        b.append("<p>Реакций под сообщениями за период не получил(а).</p>")
    else:
        rows = [[i, emoji_html(x.key, info, imgs), int(x.n), pct(x.n / recv)]
                for i, x in enumerate(mine.head(8).itertuples(), start=1)]
        b.append("<h3>Какие реакции получает чаще всего</h3>")
        b.append(table(["№", "Эмодзи", "Реакций", "Доля"], rows, num_cols=(0, 2, 3)))
        if len(mine) > 8:
            b.append(f'<p class="muted">Показаны 8 из {len(mine)} разных эмодзи.</p>')

    if full:
        gv = ds.reaction_given[ds.reaction_given["uid"] == uid].sort_values("n", ascending=False, kind="stable")
        if not gv.empty:
            total = int(gv["n"].sum())
            rows = [[i, emoji_html(x.key, info, imgs), int(x.n), pct(x.n / total)]
                    for i, x in enumerate(gv.head(8).itertuples(), start=1)]
            b.append("<h3>Какие реакции ставит чаще всего</h3>")
            b.append(table(["№", "Эмодзи", "Реакций", "Доля"], rows, num_cols=(0, 2, 3)))

        pr = ds.reaction_pairs
        if len(pr):
            names = names_map(ds)

            def nm(u):
                return names.get(u) or u

            out_df = pr[pr["src"] == uid].sort_values("n", ascending=False, kind="stable").head(5)
            in_df = pr[pr["dst"] == uid].sort_values("n", ascending=False, kind="stable").head(5)
            if not out_df.empty:
                b.append("<h3>Кому чаще всего ставит реакции</h3>")
                b.append(table(["Пользователь", "Реакций"],
                               [[nm(x.dst), int(x.n)] for x in out_df.itertuples()], num_cols=(1,)))
            if not in_df.empty:
                b.append("<h3>Кто чаще всего ставит ему реакции</h3>")
                b.append(table(["Пользователь", "Реакций"],
                               [[nm(x.src), int(x.n)] for x in in_df.itertuples()], num_cols=(1,)))

    note = "Реакции — снимок на момент сбора. "
    note += ("В режиме «счётчики» в числа входят реакции ботов и самореакции."
             if not full else "Реакции ботов и самореакции исключены.")
    b.append(f'<p class="muted">{esc(note)}</p>')
    if r["reliability"] == "низкая":
        b.append('<p class="muted">Данных об этом человеке мало: доли ориентировочные.</p>')
    return "".join(b)