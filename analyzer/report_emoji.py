"""Этап 5: раздел «Эмодзи» для HTML-отчётов. Показывается только если в файле есть данные об эмодзи."""

from avatars import fetch_emoji
from emoji_tools import display_unicode, info_map
from report_html import Raw, _bad, _link, card, esc, h2, num, pct, table

STYLE = """<style>
img.emo{display:inline-block;width:24px;height:24px;max-width:none;margin:0 6px 0 0;border:0;
border-radius:0;background:none;vertical-align:middle}
.emo-u{font-size:22px;line-height:1;margin-right:6px;vertical-align:middle;
font-family:"Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif}
.emo-name{vertical-align:middle}
.ext{color:var(--muted);font-size:12px;vertical-align:middle}
.bar{display:inline-block;height:8px;background:var(--accent);border-radius:4px;vertical-align:middle}
</style>"""

TOP_HEAD = ["№", "Эмодзи", "Использований", "Доля", "", "Людей", "Из них в «только эмодзи»"]
TOP_NUM = (0, 2, 3, 5, 6)

class EmojiImages:
    """Скачивает картинки кастомных эмодзи не чаще одного раза на ID; общий кэш на весь запуск."""

    def __init__(self, enabled: bool = True, limit: int = 150, max_fail_streak: int = 5):
        self.enabled = enabled
        self.limit = limit
        self.max_fail_streak = max_fail_streak
        self.cache: dict = {}
        self.fetched = 0
        self.fail_streak = 0

    def get(self, key: str):
        if not self.enabled or not key.startswith("c:"):
            return None
        cid = key[2:]
        if cid in self.cache:
            return self.cache[cid]
        if self.fetched >= self.limit:
            return None
        self.fetched += 1
        uri = fetch_emoji(cid)
        self.cache[cid] = uri
        if uri:
            self.fail_streak = 0
        else:
            self.fail_streak += 1
            if self.fail_streak >= self.max_fail_streak:
                self.enabled = False          # похоже, нет сети: дальше не пытаемся
        return uri

def emoji_html(key: str, info: dict, imgs: EmojiImages) -> Raw:
    name, _anim, ext = info.get(key, ("", 0, 0))
    tail = ' <span class="ext">(внешний)</span>' if ext else ""
    if key.startswith("c:"):
        uri = imgs.get(key)
        pic = f'<img class="emo" alt="" src="{uri}">' if uri else ""
        return Raw(f'{pic}<span class="emo-name">{esc(":" + (name or key[2:]) + ":")}</span>{tail}')
    return Raw(f'<span class="emo-u">{esc(display_unicode(key[2:]))}</span>{tail}')

def _top_rows(df, info, imgs, n: int) -> list:
    if df is None or df.empty:
        return []
    top = df.head(n)
    mx = float(top["uses"].max()) or 1.0
    rows = []
    for i, (key, r) in enumerate(top.iterrows(), start=1):
        w = 120 * float(r["uses"]) / mx
        rows.append([i, emoji_html(key, info, imgs), int(r["uses"]), pct(r["share"]),
                     Raw(f'<span class="bar" style="width:{w:.0f}px"></span>'),
                     int(r["users"]), int(r["only_uses"])])
    return rows

def build_server_emoji_html(ds, em, um, linked, imgs) -> str:
    if not em or not em.get("available"):
        return ""
    info = info_map(ds.emoji_info)
    b = [STYLE, h2("Эмодзи", em["rel"])]

    b.append('<div class="cards">' + "".join([
        card("Эмодзи использовано", num(em["uses"]), f"разных: {em['distinct']}"),
        card("Сообщений «только эмодзи»", num(em["only_msgs"]), f"{pct(em['only_share'])} от всех"),
        card("Людей с эмодзи", num(em["users_with"]), pct(em["users_with_share"])),
    ]) + "</div>")

    if em["empty"]:
        b.append('<div class="box">Эмодзи в сообщениях за период не найдено.</div>')
    else:
        b.append("<h3>Из чего состоят эмодзи</h3>")
        b.append(table(["Тип", "Разных", "Использований", "Доля"],
                       [[name, d, num(u), pct(s)] for name, d, u, s in em["categories"]],
                       num_cols=(1, 2, 3)))

        b.append("<h3>Самые частые эмодзи (все)</h3>")
        b.append(table(TOP_HEAD, _top_rows(em["top"], info, imgs, 15), num_cols=TOP_NUM))

        if em["top_own"] is not None and len(em["top_own"]):
            b.append("<h3>Свои кастомные эмодзи</h3>")
            b.append(table(TOP_HEAD, _top_rows(em["top_own"], info, imgs, 10), num_cols=TOP_NUM))
        if em["top_ext"] is not None and len(em["top_ext"]):
            b.append("<h3>Внешние кастомные эмодзи (внешний)</h3>")
            b.append(table(TOP_HEAD, _top_rows(em["top_ext"], info, imgs, 10), num_cols=TOP_NUM))

        b.append("<h3>Самые массовые (по числу людей)</h3>")
        b.append(table(TOP_HEAD, _top_rows(em["top_users"], info, imgs, 15), num_cols=TOP_NUM))

        lv = em.get("lovers")
        if lv is not None and len(lv):
            b.append("<h3>Любители эмодзи</h3>")
            b.append('<p class="muted">Только люди с достаточным числом сообщений; '
                     "порядок — по числу эмодзи на одно сообщение.</p>")
            rows = []
            for i, (uid, r) in enumerate(lv.iterrows(), start=1):
                fav = emoji_html(r["emoji_top_key"], info, imgs) if r["emoji_top_key"] else "—"
                rows.append([i, _link(uid, r["name"], linked), int(r["messages"]),
                             f"{r['emoji_per_msg']:.2f}", pct(r["emoji_only_share"]), fav,
                             r["reliability"]])
            b.append(table(["№", "Пользователь", "Сообщений", "Эмодзи на сообщение",
                            "Доля «только эмодзи»", "Любимый эмодзи", "Достоверность"],
                           rows, num_cols=(0, 2, 3, 4)))

    b.append('<div class="box muted"><b>Как читать:</b><ul>'
             + "".join(f"<li>{esc(x)}</li>" for x in em["rel"]["notes"]) + "</ul></div>")
    return "".join(b)

def build_user_emoji_html(ds, uid, um, em, imgs) -> str:
    if not em or not em.get("available") or uid not in um.index:
        return ""
    r = um.loc[uid]
    if _bad(r["emoji_uses"]):
        return ""
    info = info_map(ds.emoji_info)
    uses = int(r["emoji_uses"])
    b = [STYLE, h2("Эмодзи")]
    b.append('<div class="cards">' + "".join([
        card("Эмодзи использовано", num(uses), f"разных: {int(r['emoji_distinct'])}"),
        card("Эмодзи на сообщение", num(r["emoji_per_msg"], 2)),
        card("Сообщений «только эмодзи»", num(r["emoji_only_msgs"]), pct(r["emoji_only_share"])),
        card("Сообщений с текстом", num(r["content_msgs"]), "не только эмодзи"),
        card("Дней с текстом", num(r["content_days"]), f"из {int(r['active_days'])} активных"),
    ]) + "</div>")

    mine = ds.emoji_user[ds.emoji_user["uid"] == uid]
    if uses == 0 or mine.empty:
        b.append("<p>Эмодзи за период не использовал(а).</p>")
        return "".join(b)

    g = mine.groupby("key").agg(n=("n", "sum"))
    g["only"] = mine[mine["only"] == 1].groupby("key")["n"].sum().reindex(g.index).fillna(0)
    g = g.sort_values("n", ascending=False, kind="stable")
    rows = [[i, emoji_html(key, info, imgs), int(x["n"]), pct(x["n"] / uses), int(x["only"])]
            for i, (key, x) in enumerate(g.head(8).iterrows(), start=1)]
    b.append("<h3>Любимые эмодзи</h3>")
    b.append(table(["№", "Эмодзи", "Использований", "Доля", "Из них в «только эмодзи»"],
                   rows, num_cols=(0, 2, 3, 4)))
    if len(g) > 8:
        b.append(f'<p class="muted">Показаны 8 из {len(g)} разных эмодзи.</p>')
    if r["reliability"] == "низкая":
        b.append('<p class="muted">Данных об этом человеке мало: доли ориентировочные.</p>')
    return "".join(b)