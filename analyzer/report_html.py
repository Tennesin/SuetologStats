"""Этап 5: HTML-отчёты (один файл, картинки вшиты в base64)."""

import html
from datetime import datetime, timedelta
from urllib.parse import quote

import numpy as np

import charts as C
import metrics as M
import settings as S

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2430;--muted:#6b7380;--line:#e3e6eb;--accent:#1F4E78}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:24px 16px 60px}
h1{margin:0 0 4px;font-size:26px}
h2{margin:32px 0 10px;font-size:19px;color:var(--accent);border-bottom:2px solid var(--line);padding-bottom:6px}
.muted{color:var(--muted);font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.card .v{font-size:22px;font-weight:700}
.card .l{font-size:12px;color:var(--muted)}
.card .h{font-size:12px;color:var(--muted)}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:12px 0}
.warn{border-color:#e0b252;background:#fff8e5}
table{border-collapse:collapse;width:100%;background:var(--card);font-size:14px;margin:8px 0}
th{background:var(--accent);color:#fff;text-align:left;padding:6px 8px;font-weight:600}
td{border-bottom:1px solid var(--line);padding:5px 8px;vertical-align:top}
tr:nth-child(even) td{background:#fafbfc}
td.n,th.n{text-align:right}
.tblwrap{overflow-x:auto}
img{max-width:100%;height:auto;display:block;margin:10px auto;border:1px solid var(--line);border-radius:8px;background:#fff}
.badge{display:inline-block;padding:1px 9px;border-radius:10px;font-size:12px;font-weight:600;color:#fff}
.b-hi{background:#2E9E5B}.b-mid{background:#d89b1d}.b-lo{background:#c9443f}
a{color:var(--accent)}
ul{margin:6px 0 6px 20px;padding:0}
details{margin:14px 0}
summary{cursor:pointer;font-weight:600}
.head{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:8px}
.avatar{width:96px;height:96px;border-radius:50%;object-fit:cover;margin:0;flex:none;border:2px solid var(--line);background:#fff}
.avatar.ph{display:flex;align-items:center;justify-content:center;background:var(--accent);color:#fff;font-size:42px;font-weight:700}
.spec{border-left:4px solid var(--accent)}
.spec p{margin:6px 0 0}
"""

_REL_CLASS = {"высокая": "hi", "средняя": "mid", "низкая": "lo"}


class Raw(str):
    """Готовый HTML: не экранируется."""


# ---------- Мелкие помощники ----------

def esc(x) -> str:
    return html.escape(str(x), quote=True)


def _bad(x) -> bool:
    return x is None or (isinstance(x, float) and x != x)


def num(x, d: int = 0) -> str:
    if _bad(x):
        return "—"
    return f"{x:,.{d}f}".replace(",", " ")


def pct(x, sign: bool = False) -> str:
    if _bad(x):
        return "—"
    return f"{x * 100:+.1f}%" if sign else f"{x * 100:.1f}%"


def badge(level: str) -> str:
    return f'<span class="badge b-{_REL_CLASS.get(level, "lo")}">{esc(level)}</span>'


def ul(items) -> str:
    return "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"


def h2(text: str, rel=None) -> str:
    extra = f' <span class="muted">достоверность:</span> {badge(rel["level"])}' if rel else ""
    return f"<h2>{esc(text)}{extra}</h2>"


def card(label, value, hint: str = "") -> str:
    h = f'<div class="h">{esc(hint)}</div>' if hint else ""
    return f'<div class="card"><div class="l">{esc(label)}</div><div class="v">{esc(value)}</div>{h}</div>'


def img(png, alt: str) -> str:
    if png is None:
        return ""
    return f'<img alt="{esc(alt)}" src="data:image/png;base64,{C.b64(png)}">'


def _cell(v) -> str:
    return str(v) if isinstance(v, Raw) else esc(v)


def table(headers, rows, num_cols=()) -> str:
    th = "".join(
        f'<th class="n">{esc(h)}</th>' if i in num_cols else f"<th>{esc(h)}</th>"
        for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(
            f'<td class="n">{_cell(v)}</td>' if i in num_cols else f"<td>{_cell(v)}</td>"
            for i, v in enumerate(r)) + "</tr>"
        for r in rows)
    return f'<div class="tblwrap"><table><tr>{th}</tr>{body}</table></div>'


def page(title: str, body: str) -> str:
    stamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(title)}</title><style>{CSS}</style></head><body><div class=\"wrap\">"
        f'{body}<p class="muted">Сформировано: {stamp}</p></div></body></html>'
    )


def _link(uid, name, linked, prefix: str = "users/"):
    if uid in linked:
        return Raw(f'<a href="{prefix}{quote(linked[uid])}">{esc(name)}</a>')
    return name

def _week_range(monday, ds) -> str:
    """Подпись недели: границы подрезаны по окну анализа, например «27.09 – 27.09»."""
    start, end = monday, monday + timedelta(days=6)
    a, b = ds.window
    if a and start < a:
        start = a
    if b and end > b:
        end = b
    return f"{start:%d.%m} – {end:%d.%m}"

def _trend_lines(tr) -> list:
    pk, w = tr["peak"], tr["window"]
    lines = [
        f"Последние {w} дн.: {num(tr['last_avg'], 1)} в день; предыдущие {w} дн.: "
        f"{num(tr['prev_avg'], 1)} ({pct(tr['recent_change'], True)}).",
        f"Вторая половина окна к первой: {pct(tr['change'], True)} "
        f"(в среднем в день {num(tr['first_half_avg'], 1)} → {num(tr['second_half_avg'], 1)}).",
        f"Самая активная неделя: {pk['start']:%d.%m} – {pk['end']:%d.%m}, "
        f"{num(pk['avg'], 1)} в день, {pct(pk['share'])} всех сообщений окна.",
    ]
    if tr["direction"] == "всплеск и спад":
        fw = tr["first_week_avg"]
        lines.append(
            "Сравнение половин здесь вводит в заблуждение: его определяет эта неделя. "
            f"Последняя неделя в {pk['avg'] / max(tr['last_avg'], 1e-9):.1f} раза ниже пика"
            + (f" и составляет {pct(tr['last_avg'] / fw)} от уровня первой недели ({num(fw, 1)} в день)."
               if fw > 0 else ".")
            + " Устойчивого роста нет.")
    elif tr["direction"] == "неоднозначно":
        lines.append("Сигналы разных периодов противоположны: делать вывод о направлении рано.")
    return lines


def _trend_hint(r) -> str:
    t = r["trend"]
    if t == "пачками":
        return f"3 дня дали {pct(r['burst_share'])} сообщений"
    if t in ("растёт", "снижается", "стабильно"):
        return f"{int(r['recent_n'])} против {int(r['prev_n'])} за {int(r['trend_window'])} дн."
    if t == "притих":
        return f"нет сообщений {int(r['days_since_last'])} дн."
    return ""


def method_html() -> str:
    W = S.SKP_WEIGHTS

    def p(k):
        return f"{W[k] * 100:.0f}%"

    return f"""<details><summary>Как считаются СКП и риск потери</summary><div class="box">
<p><b>СКП</b> — значимость пользователя для сервера, число от 0 до 100: сумма шести компонентов (каждый от 0 до 1) с весами.</p>
<ul>
<li><b>V, вклад ({p('V')})</b>: ln(1+n) / ln(1+P95), где n — сообщения человека, P95 — 95-й перцентиль по серверу. Логарифм не даёт одному спамеру задавить остальных.</li>
<li><b>C, постоянство ({p('C')})</b>: {S.SKP_C_DAYS_W:.1f} × доля активных дней + {1 - S.SKP_C_DAYS_W:.1f} × доля активных недель.</li>
<li><b>R, охват ({p('R')})</b>: число каналов, где у человека не меньше {S.SKP_R_MIN_MSGS} сообщений, делённое на min({S.SKP_R_CAP}, число значимых каналов). Значимый канал — не менее {S.SKP_SIG_CHANNEL * 100:.0f}% сообщений сервера.</li>
<li><b>I, взаимодействие ({p('I')})</b>: доля ответов (reply), сглаженная к среднему по серверу, относительно потолка {S.SKP_I_CEIL}. Упоминания и реакции недоступны без привилегированного интента.</li>
<li><b>D, зависимость сервера ({p('D')})</b>: максимальная доля человека среди сообщений значимого канала; потолок — {S.SKP_D_CEIL * 100:.0f}% канала.</li>
<li><b>P, роль ({p('P')})</b>: основатель {S.SKP_ROLE['owner']}, админ {S.SKP_ROLE['admin']}, остальные 0.</li>
</ul>
<p>Динамика в СКП не входит. Если часть данных недоступна (файл старого формата), вес недостающих компонентов перераспределяется на остальные.</p>
<p><b>Риск потери</b> (справочная шкала 0–100): {S.RISK_WEIGHTS['recency'] * 100:.0f}% — давность молчания относительно обычного промежутка между активными днями человека,
{S.RISK_WEIGHTS['decline'] * 100:.0f}% — снижение темпа во второй половине окна, {S.RISK_WEIGHTS['streak'] * 100:.0f}% — прерванная серия активных дней. Показывается только для выбранных пользователей.</p>
<p class="muted">Веса и пороги заданы экспертно и пока не проверялись на эталонных данных. СКП сравнивает людей внутри одного сервера за выбранный период; это не оценка человека и не основание для санкций. При короткой истории все выводы ориентировочные.</p>
</div></details>"""


# ---------- Отчёт по серверу ----------

def build_server_html(ds, sm, um, sk, linked) -> str:
    rel = sm["reliability"]
    kind = "Суммарный отчёт" if ds.is_merged else "Отчёт по серверу"
    b = [
        f"<h1>{esc(ds.title)}</h1>",
        f'<p class="muted">{kind} · период: {esc(ds.period_text or "—")} · '
        f'окно анализа: {ds.window[0]} — {ds.window[1]} ({ds.window_days} дн.) · '
        f'часовой пояс: {esc(ds.tz or "—")}</p>',
    ]
    box = f'<b>Достоверность выводов:</b> {badge(rel["level"])}'
    if rel["notes"]:
        box += ul(rel["notes"])
    b.append(f'<div class="box">{box}</div>')
    if ds.warnings:
        b.append(f'<div class="box warn"><b>Предупреждения при чтении файла</b>{ul(ds.warnings)}</div>')
    if ds.notes:
        b.append(f'<div class="box"><b>Примечания бота</b>{ul(ds.notes)}</div>')
    if ds.excluded:
        b.append(f'<div class="box muted">Из анализа исключено чатов по правилам бота: {len(ds.excluded)}. '
                 "Их сообщения в отчёт не входят.</div>")

    if sm["empty"]:
        b.append("<p>За выбранный период сообщений нет.</p>")
        return page(f"{ds.title} — анализ", "".join(b))

    ov = sm["overview"]
    b.append('<div class="cards">' + "".join([
        card("Сообщений", num(sm["messages"])),
        card("Пользователей", num(sm["users"])),
        card("Дней в окне", sm["days"], f"с сообщениями: {ov['active_days']}"),
        card("В среднем в день", num(ov["avg_per_day"], 1), f"медиана {num(ov['median_per_day'])}"),
        card("DAU (среднее)", num(ov["avg_dau"], 1), f"максимум {ov['max_dau']}"),
        card("Доля ответов", pct(ov["reply_share"])),
        card("Пиковый день", str(ov["peak_day"]), f"{ov['peak_messages']} сообщ."),
    ]) + "</div>")

    # Динамика
    tr = sm["trend"]
    b.append(h2("Динамика активности", tr["rel"]))
    b.append(img(C.chart_timeline(sm["series"]), "Сообщения по дням"))
    b.append(img(C.chart_dau(sm["series"]), "DAU"))
    if tr["available"]:
        b.append(f"<p>Тренд: <b>{esc(tr['direction'])}</b>.</p>")
        b.append(ul(_trend_lines(tr)))
        b.append(img(C.chart_weekdays(tr["weekday_avg"]), "По дням недели"))
        rows = [[_week_range(wk, ds), int(r["messages"]), int(r["days"]),
                 num(r["messages"] / r["days"], 1)]
                for wk, r in tr["weekly"].iterrows()]
        b.append('<p class="muted">По неделям (границы подрезаны по окну анализа). Первая и последняя '
                 "недели могут быть неполными, поэтому сравнивайте их по колонке «В среднем в день».</p>")
        b.append(table(["Период", "Сообщений", "Дней", "В среднем в день"], rows,
                       num_cols=(1, 2, 3)))
    else:
        b.append(f"<p class=\"muted\">{esc(tr['rel']['notes'][0])}</p>")

    # Распределение
    d = sm["distribution"]
    b.append(h2("Распределение активности", d["rel"]))
    b.append(ul([
        f"Индекс Джини: {d['gini']:.2f} (0 — все пишут поровну, 1 — пишет один человек).",
        f"Доля топ-1: {pct(d['top1'])}, топ-5: {pct(d['top5'])}, топ-10% ({d['k10']} чел.): {pct(d['top10pct'])}.",
        f"50% сообщений пишут {d['users_for_50']} чел., 80% — {d['users_for_80']} чел.",
        f"Сообщений на человека: среднее {num(d['mean'], 1)}, медиана {num(d['median'])}, "
        f"90-й перцентиль {num(d['p90'])}, максимум {num(d['max'])}.",
    ]))
    b.append(img(C.chart_lorenz(um["messages"].values, d["gini"]), "Кривая Лоренца"))

    seg = sm["segments"]
    b.append("<h3>Сегменты пользователей</h3>")
    b.append('<p class="muted">Ядро — активны ≥50% дней окна; регулярные — 20–50%; '
             "эпизодические — менее 20%; разовые — писали в один день.</p>")
    b.append(table(["Сегмент", "Человек", "Доля людей", "Сообщений", "Доля сообщений"],
                   [[name, int(r["users"]), pct(r["user_share"]), int(r["messages"]), pct(r["message_share"])]
                    for name, r in seg.iterrows()], num_cols=(1, 2, 3, 4)))
    b.append(img(C.chart_segments(seg), "Сегменты"))

    # Время
    t = sm["time"]
    if t:
        b.append(h2("Время активности", t["rel"]))
        b.append(ul([
            f"Пик по часам: {t['peak_hour']:02d}:00; самый активный день недели: {S.WEEKDAYS[t['peak_weekday']]}.",
            f"Самые активные 3 часа подряд: с {t['best3_start']:02d}:00 ({pct(t['best3_share'])} сообщений).",
            f"Ночью (00–06): {pct(t['night_share'])}; в выходные: {pct(t['weekend_share'])}.",
        ]))
        b.append(img(C.chart_heatmap(t["matrix"], ds.tz), "Тепловая карта"))

    # Каналы
    chn = sm["channels"]
    if chn:
        b.append(h2("Каналы", chn["rel"]))
        b.append(ul([
            f"Топ-3 канала дают {pct(chn['top3_share'])} сообщений.",
            f"Пишут только в одном канале: {pct(chn['single_channel_share'])} пользователей; "
            f"в среднем каналов на человека: {chn['mean_channels']:.1f}.",
        ]))
        b.append(img(C.chart_channels(chn["table"]), "Топ каналов"))
        b.append(table(["Канал", "Сообщений", "Доля", "Авторов"],
                       [[r["channel"], int(r["messages"]), pct(r["share"]), int(r["authors"])]
                        for _cid, r in chn["table"].head(15).iterrows()], num_cols=(1, 2, 3)))

    # Жизненный цикл и сравнение
    lc = sm["lifecycle"]
    b.append(h2("Жизненный цикл", lc["rel"]))
    items = [f"Притихли (нет сообщений последние {M.DORMANT_DAYS} дн. окна): {lc['dormant']} чел. ({pct(lc['dormant_share'])})."]
    items.append(f"Писали уже в первый день окна ({ds.window[0]}): {lc['from_start']} чел. "
                 "Это стартовая аудитория, а не приток новых.")
    if "retained" in lc:
        items.append(f"Писали в обеих половинах окна: {lc['retained']} чел.; только в первой: {lc['lost']}; "
                     f"только во второй: {lc['new_second_half']}; удержание: {pct(lc.get('retention'))}.")
    b.append(ul(items))
    b.append(ul(lc["rel"]["notes"]))
    if lc["new_by_week"]:
        b.append("<p class=\"muted\">Впервые написали после первого дня окна, по неделям:</p>")
        b.append(table(["Период", "Впервые написали"],
                       [[_week_range(wk, ds), v] for wk, v in sorted(lc["new_by_week"].items())],
                       num_cols=(1,)))

    cp = sm["compare"]
    if cp:
        b.append(h2("Сравнение с предыдущим периодом", cp["rel"]))
        b.append(ul([
            f"Сообщения: {num(cp['prev_messages'])} → {num(sm['messages'])} ({pct(cp['messages_change'], True)}).",
            f"Пользователи: {num(cp['prev_users'])} → {num(sm['users'])} ({pct(cp['users_change'], True)}).",
            f"Писали в обоих периодах: {cp['retained']}; новых: {cp['new']}; не писавших сейчас: {cp['lost']}; "
            f"удержание: {pct(cp['retention'])}.",
        ]))
        b.append(ul(cp["rel"]["notes"]))

    # Серверы (суммарный файл)
    sv = sm["servers"]
    if sv:
        b.append(h2("Серверы"))
        b.append(f"<p>Пишут на нескольких серверах: {sv['multi_server_users']} чел. "
                 f"({pct(sv['multi_server_share'])}).</p>")
        b.append(table(["Сервер", "Сообщений", "Доля", "Авторов"],
                       [[srv, int(r["messages"]), pct(r["share"]), int(r["authors"])]
                        for srv, r in sv["table"].iterrows()], num_cols=(1, 2, 3)))

    # Администрация
    if len(ds.staff):
        st = sm["staff"]
        b.append(h2("Администрация"))
        if st:
            b.append(f"<p>{st['people']} чел. написали {num(st['messages'])} сообщений — "
                     f"{pct(st['share'])} от всех.</p>")
        s2 = ds.staff.copy()
        s2["k"] = s2["kind"].map({"owner": 0, "admin": 1})
        s2 = s2.sort_values(["server", "k", "n"], ascending=[True, True, False])
        b.append(table(["Сервер", "Пользователь", "Должность", "Роли", "Сообщений"],
                       [[r.server, r.name, S.KIND_RU.get(r.kind, r.kind), r.roles or "—", int(r.n)]
                        for r in s2.itertuples()], num_cols=(4,)))

    # СКП
    if len(sk):
        b.append(h2("СКП: значимость пользователей", rel))
        b.append('<p class="muted">В таблице — выбранные пользователи: топ по СКП и все, у кого СКП выше порога '
                 "(для них есть индивидуальные отчёты). Знак «≈» — данных о человеке мало. "
                 "Полный список — в сводном xlsx.</p>")
        b.append(img(C.chart_skp_top(sk, um), "Топ по СКП"))
        rows = []
        for uid, s in sk[sk["selected"]].iterrows():
            r = um.loc[uid]
            low = r["reliability"] == "низкая"
            risk = "—" if _bad(s["risk"]) else f"{s['risk']:.0f} ({s['risk_level']})"
            rows.append([int(s["skp_rank"]), _link(uid, r["name"], linked),
                         f"{s['skp']:.1f}" + (" ≈" if low else ""), s["skp_level"],
                         int(r["messages"]), int(r["active_days"]), risk, r["reliability"], r["role"]])
        b.append(table(["№", "Пользователь", "СКП", "Уровень", "Сообщений", "Дней", "Риск потери",
                        "Достоверность", "Роль"], rows, num_cols=(0, 2, 4, 5)))
        b.append(method_html())

    return page(f"{ds.title} — анализ", "".join(b))


# ---------- Индивидуальный отчёт ----------

def _explain(ds, um, uid, r, D) -> dict:
    p95 = float(np.percentile(um["messages"], S.SKP_V_PERCENTILE))
    ch = ds.channels
    cnt = int(((ch["uid"] == uid) & (ch["n"] >= S.SKP_R_MIN_MSGS)).sum()) if len(ch) else None
    m = float(um["replies"].sum()) / float(um["messages"].sum()) if um["messages"].sum() else 0.0
    return {
        "V": f"{int(r['messages'])} сообщений; потолок — 95-й перцентиль сервера ({p95:.0f})",
        "C": f"активных дней {int(r['active_days'])} из {D} ({pct(r['active_share'])}); "
             f"недель {int(r['weeks_active'])} ({pct(r['weeks_share'])})",
        "R": (f"каналов, где ≥{S.SKP_R_MIN_MSGS} сообщений: {cnt}" if cnt is not None
              else "нет данных по каналам (файл старого формата)"),
        "I": (f"ответов {int(r['replies'])} из {int(r['messages'])} ({pct(r['reply_share'])}); "
              f"среднее по серверу {pct(m)}" if ds.full_data else "нет данных (файл старого формата)"),
        "D": f"доля человека среди сообщений значимого канала; максимум при ≥{S.SKP_D_CEIL * 100:.0f}% канала",
        "P": r["role"] or "без роли администрации",
    }


def build_user_html(ds, uid, um, sk, days, avatar=None) -> str:
    r, s = um.loc[uid], sk.loc[uid]
    D = len(days)
    W = S.SKP_WEIGHTS
    b = ['<p class="muted"><a href="../report.html">← к отчёту по серверу</a></p>']
    sub = [x for x in (f"@{r['username']}" if r["username"] else "", f"ID {uid}", r["role"],
                       ds.title, ds.period_text) if x]

    if avatar:
        av = f'<img class="avatar" alt="" src="{avatar}">'
    else:
        letter = (str(r["name"]).strip() or "?")[0].upper()
        av = f'<div class="avatar ph">{esc(letter)}</div>'
    b.append(f'<div class="head"><div><h1>{esc(r["name"])}</h1>'
             f'<p class="muted">{esc(" · ".join(sub))}</p></div>{av}</div>')

    # Особая информация (заполняется вручную в settings.SPEC_INFO)
    spec = S.SPEC_INFO_BY_ID.get(str(uid))
    if spec:
        spec_html = esc(spec).replace(chr(10), "<br>")
        b.append(f'<div class="box spec"><b>Особая информация</b><p>{spec_html}</p></div>')

    lvl = r["reliability"]
    box = f"<b>Достоверность выводов:</b> {badge(lvl)}"
    if lvl == "низкая":
        box += "<br>Данных об этом человеке мало (сообщений или активных дней): оценки ниже ориентировочные."
    if r["burst_share"] >= M.BURST_TOP3_SHARE and r["active_days"] >= M.MIN_USER_ACTIVE_DAYS_TREND:
        box += (f"<br>Активность пачками: три самых активных дня дали {pct(r['burst_share'])} "
                "сообщений, поэтому выводы о динамике и привычном времени ориентировочные.")
    if ds.incomplete:
        box += "<br>Сбор данных был остановлен вручную: все цифры неполные."
    if ds.filtered:
        box += f"<br>Отчёт построен с фильтром ({esc(ds.filtered)}): это не весь сервер."
    b.append(f'<div class="box">{box}</div>')

    cards = [
        card("СКП", num(s["skp"], 1), s["skp_level"]),
        card("Место по сообщениям", f"{int(r['rank'])} из {len(um)}"),
        card("Сообщений", num(r["messages"]), f"{pct(r['server_share'])} от всех"),
        card("Активных дней", f"{int(r['active_days'])} из {D}", pct(r["active_share"])),
        card("В активный день", num(r["avg_per_active_day"], 1), f"максимум {int(r['max_day'])}"),
        card("Серия подряд", f"{int(r['longest_streak'])} дн.", f"сейчас {int(r['current_streak'])}"),
        card("Недель активно", int(r["weeks_active"]), pct(r["weeks_share"])),
        card("Последнее сообщение", str(r["last_date"]), f"{int(r['days_since_last'])} дн. до конца окна"),
        card("Тренд", r["trend"], _trend_hint(r)),
    ]
    if ds.full_data:
        cards.append(card("Ответы", pct(r["reply_share"]), f"{int(r['replies'])} шт."))
    b.append('<div class="cards">' + "".join(cards) + "</div>")

    # Компоненты СКП
    b.append(h2("Из чего сложился СКП"))
    expl = _explain(ds, um, uid, r, D)
    rows = []
    for k in "VCRIDP":
        v = s[k]
        rows.append([k, S.SKP_NAMES[k], "н/д" if _bad(v) else f"{v:.2f}", f"{W[k] * 100:.0f}%",
                     "—" if _bad(v) else f"{W[k] * v * 100:.1f}", expl[k]])
    rows.append(["", "Итого", "", "100%", f"{s['skp']:.1f}", ""])
    b.append(table(["", "Компонент", "Значение (0–1)", "Вес", "Баллы", "Пояснение"], rows, num_cols=(2, 3, 4)))
    if s["skp_partial"]:
        b.append('<p class="muted">Часть компонентов недоступна, поэтому их вес перераспределён: '
                 "сумма баллов в таблице может не совпадать с итоговым СКП.</p>")

    # Риск потери
    if s["selected"]:
        b.append(h2("Риск потери (справочно)"))
        b.append(f"<p>Риск: <b>{s['risk']:.0f}</b> из 100 ({esc(s['risk_level'])}). "
                 "Это не прогноз ухода человека, а сигнал присмотреться: он учитывает только "
                 "молчание, падение темпа и прерванную серию.</p>")
        b.append(table(["Составляющая", "Значение (0–1)", "Вес"],
                       [["Давность молчания", "н/д" if _bad(s["risk_recency"]) else f"{s['risk_recency']:.2f}",
                         f"{S.RISK_WEIGHTS['recency'] * 100:.0f}%"],
                        ["Снижение темпа", "н/д" if _bad(s["risk_decline"]) else f"{s['risk_decline']:.2f}",
                         f"{S.RISK_WEIGHTS['decline'] * 100:.0f}%"],
                        ["Прерванная серия", "н/д" if _bad(s["risk_streak"]) else f"{s['risk_streak']:.2f}",
                         f"{S.RISK_WEIGHTS['streak'] * 100:.0f}%"]], num_cols=(1, 2)))

    # Графики
    b.append(h2("Активность"))
    mine = ds.daily[ds.daily["uid"] == uid].set_index("date")["n"].reindex(days, fill_value=0)
    b.append(img(C.chart_user_days(mine, r["name"]), "Сообщения по дням"))
    b.append(img(C.chart_user_hours(ds, uid), "Профиль по часам"))
    if not _bad(r["peak_hour"]):
        wd = ("" if _bad(r["peak_weekday"])
              else f", чаще всего в день недели {S.WEEKDAYS[int(r['peak_weekday'])]}")
        b.append(f"<p>Чаще всего пишет около {int(r['peak_hour']):02d}:00{wd}; "
                 f"ночью — {pct(r['night_share'])}, в выходные — {pct(r['weekend_share'])} "
                 f"(часовой пояс {esc(ds.tz or '—')}).</p>")

    # Каналы
    chn = ds.channels
    if len(chn):
        mine_ch = chn[chn["uid"] == uid].sort_values("n", ascending=False)
        total = mine_ch["n"].sum()
        if total:
            b.append(h2("Где пишет"))
            b.append(table(["Канал", "Сообщений", "Доля"],
                           [[x.channel, int(x.n), pct(x.n / total)] for x in mine_ch.head(8).itertuples()],
                           num_cols=(1, 2)))
            if len(mine_ch) > 8:
                b.append(f'<p class="muted">Показаны 8 из {len(mine_ch)} каналов.</p>')

    return page(f"{r['name']} — индивидуальный отчёт", "".join(b))