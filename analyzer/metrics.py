"""Этап 2: метрики сервера и пользователей. Работает только с Dataset, без Discord и сети."""

import math

import numpy as np
import pandas as pd

from loader import Dataset

LEVELS = ["низкая", "средняя", "высокая"]
NIGHT_HOURS = 6            # ночь: часы 0..5
DORMANT_DAYS = 7           # «притих»: нет сообщений последние N дней окна
MIN_TREND_DAYS = 14        # меньше — тренды не считаем
MIN_USER_MSGS_TREND = 20   # меньше сообщений — тренд пользователя не оцениваем
TREND_UP = 1.3
TREND_DOWN = 0.7


# ---------- Вспомогательное ----------

def _lvl(value, mid, high) -> int:
    return 2 if value >= high else 1 if value >= mid else 0


def make_rel(level: int, notes: list) -> dict:
    level = max(0, min(2, int(level)))
    return {"level": LEVELS[level], "notes": notes}


def calendar_days(ds: Dataset) -> pd.DatetimeIndex:
    """Все календарные дни окна анализа (заявленный период, расширенный фактическими данными)."""
    a, b = ds.window
    if ds.data_start:
        a = min(a, ds.data_start) if a else ds.data_start
    if ds.data_end:
        b = max(b, ds.data_end) if b else ds.data_end
    if not a or not b:
        return pd.DatetimeIndex([])
    return pd.date_range(a, b, freq="D")


def gini(values) -> float:
    x = np.sort(np.asarray(values, dtype=float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return 0.0
    cum = np.cumsum(x)
    return float((n + 1 - 2 * cum.sum() / cum[-1]) / n)


def _top_share(desc: np.ndarray, k: int, total: float) -> float:
    return float(desc[:k].sum() / total) if total else 0.0


def base_reliability(ds: Dataset, days_n: int, users_n: int) -> dict:
    notes, lv = [], min(_lvl(days_n, 14, 28), _lvl(ds.total_messages, 300, 2000), _lvl(users_n, 10, 30))
    if days_n < 14:
        notes.append(f"короткое окно ({days_n} дн.): тренды и сезонность ненадёжны")
    if ds.total_messages < 300:
        notes.append("мало сообщений: доли и распределения шумные")
    if users_n < 10:
        notes.append("мало пользователей: распределения и сегменты неустойчивы")
    if ds.incomplete:
        lv -= 1
        notes.append("сбор остановлен вручную: данные неполные")
    if ds.truncated:
        lv -= 1
        notes.append("данные по дням обрезаны лимитом строк")
    if getattr(ds, "filtered", ""):
        lv = 0
        notes.append("отчёт с фильтром, это не весь сервер: " + ds.filtered)
    return make_rel(lv, notes)


# ---------- Блоки метрик сервера ----------

def _trend_block(tot: pd.Series, D: int) -> dict:
    if D < MIN_TREND_DAYS:
        return {"available": False, "rel": make_rel(0, [f"окно {D} дн. < {MIN_TREND_DAYS}: тренд не оценивается"])}
    h = D // 2
    first, second = float(tot.iloc[:h].mean()), float(tot.iloc[h:].mean())
    change = (second / first - 1) if first > 0 else None
    mean = float(tot.mean())
    slope = float(np.polyfit(np.arange(D), tot.values.astype(float), 1)[0])
    if change is None:
        direction = "н/д"
    elif change > 0.15:
        direction = "рост"
    elif change < -0.15:
        direction = "спад"
    else:
        direction = "стабильно"
    wk = tot.groupby(tot.index.to_period("W")).agg(["sum", "count"])
    wk.index = [p.start_time.date() for p in wk.index]
    wk.columns = ["messages", "days"]
    wd = tot.groupby(tot.index.weekday).mean().reindex(range(7)).fillna(0.0)
    notes = ["неполные недели по краям окна не сопоставимы с полными (см. колонку days)"]
    return {
        "available": True, "direction": direction, "change": change,
        "first_half_avg": first, "second_half_avg": second,
        "slope_rel": (slope / mean) if mean > 0 else None,
        "weekly": wk, "weekday_avg": [float(v) for v in wd.values],
        "rel": make_rel(_lvl(D, 14, 28), notes),
    }


def _time_block(ds: Dataset):
    ht = ds.heat_total
    if ht is None or ht.empty or ht["n"].sum() == 0:
        return None
    m = np.zeros((7, 24))
    for r in ht.itertuples(index=False):
        if 0 <= r.weekday < 7 and 0 <= r.hour < 24:
            m[r.weekday, r.hour] += r.n
    total = m.sum()
    if total == 0:
        return None
    hour_tot, wd_tot = m.sum(axis=0), m.sum(axis=1)
    sums = [sum(hour_tot[(h + k) % 24] for k in range(3)) for h in range(24)]
    start = int(np.argmax(sums))
    return {
        "matrix": m, "peak_hour": int(hour_tot.argmax()), "peak_weekday": int(wd_tot.argmax()),
        "night_share": float(hour_tot[:NIGHT_HOURS].sum() / total),
        "weekend_share": float(wd_tot[5:].sum() / total),
        "best3_start": start, "best3_share": float(sums[start] / total),
        "rel": make_rel(_lvl(total, 300, 2000), ["часовой пояс: " + (ds.tz or "не указан")]),
    }


def _segments(active_days: pd.Series, per_user: pd.Series, D: int) -> pd.DataFrame:
    ad = active_days.reindex(per_user.index).values
    share = ad / D
    seg = np.select(
        [ad == 1, share >= 0.5, share >= 0.2],
        ["разовые", "ядро", "регулярные"], default="эпизодические")
    total = float(per_user.sum())
    rows = []
    for name in ["ядро", "регулярные", "эпизодические", "разовые"]:
        mask = seg == name
        msgs = float(per_user.values[mask].sum())
        rows.append((name, int(mask.sum()), mask.sum() / len(per_user),
                     int(msgs), msgs / total if total else 0.0))
    return pd.DataFrame(rows, columns=["segment", "users", "user_share", "messages", "message_share"]
                        ).set_index("segment")


def server_metrics(ds: Dataset) -> dict:
    days = calendar_days(ds)
    D = len(days)
    daily = ds.daily
    if daily.empty or D == 0:
        return {"empty": True, "reliability": make_rel(0, ["нет сообщений за период"])}

    total_msgs = int(daily["n"].sum())
    per_user = daily.groupby("uid")["n"].sum()
    U = len(per_user)
    g = daily.groupby("uid")["date"].agg(["min", "max", "nunique"])

    out = {"empty": False, "days": D, "messages": total_msgs, "users": U,
           "reliability": base_reliability(ds, D, U)}

    # Ряды по дням
    tot = daily.groupby("date")["n"].sum().reindex(days, fill_value=0)
    dau = daily.groupby("date")["uid"].nunique().reindex(days, fill_value=0)
    out["series"] = pd.DataFrame({"messages": tot, "dau": dau})

    replies_total = int(ds.users["replies"].sum()) if ds.full_data and len(ds.users) else None
    out["overview"] = {
        "active_days": int((tot > 0).sum()),
        "avg_per_day": total_msgs / D,
        "median_per_day": float(tot.median()),
        "peak_day": tot.idxmax().date(), "peak_messages": int(tot.max()),
        "avg_dau": float(dau.mean()), "max_dau": int(dau.max()),
        "stickiness": float(dau.mean() / U),
        "msgs_per_user_mean": total_msgs / U,
        "msgs_per_user_median": float(per_user.median()),
        "reply_share": (replies_total / total_msgs) if replies_total is not None else None,
    }
    out["trend"] = _trend_block(tot, D)

    # Распределение
    vals = np.sort(per_user.values.astype(float))[::-1]
    total = float(vals.sum())
    cum = np.cumsum(vals)
    k10 = max(1, math.ceil(0.1 * U))
    out["distribution"] = {
        "gini": gini(vals), "top1": _top_share(vals, 1, total), "top5": _top_share(vals, 5, total),
        "top10pct": _top_share(vals, k10, total), "k10": k10,
        "users_for_50": int(np.searchsorted(cum, 0.5 * total, side="left") + 1),
        "users_for_80": int(np.searchsorted(cum, 0.8 * total, side="left") + 1),
        "mean": float(vals.mean()), "median": float(np.median(vals)),
        "p90": float(np.percentile(vals, 90)), "max": int(vals[0]),
        "rel": make_rel(_lvl(U, 10, 30), []),
    }
    out["segments"] = _segments(g["nunique"], per_user, D)
    out["time"] = _time_block(ds)

    # Жизненный цикл
    first_seen = g["min"]
    from_start = int((first_seen == days[0]).sum())
    later = first_seen[first_seen > days[0]]
    nbw = later.dt.to_period("W").value_counts().sort_index()
    life = {
        "from_start": from_start,
        "new_by_week": {p.start_time.date(): int(v) for p, v in nbw.items()},
    }
    if D >= MIN_TREND_DAYS:
        half = days[D // 2]
        early = set(daily.loc[daily["date"] < half, "uid"])
        late = set(daily.loc[daily["date"] >= half, "uid"])
        life.update(
            retained=len(early & late), lost=len(early - late), new_second_half=len(late - early),
            retention=(len(early & late) / len(early)) if early else None)
    since = (days[-1] - g["max"]).dt.days
    dormant = int((since >= DORMANT_DAYS).sum())
    life.update(dormant=dormant, dormant_share=dormant / U)
    life["rel"] = make_rel(_lvl(D, 14, 28), [
        "«первое появление» = первое сообщение в окне, а не вступление на сервер",
        f"«притих» = нет сообщений последние {DORMANT_DAYS} дн. окна"])
    out["lifecycle"] = life

    # Сравнение с прошлым периодом
    out["compare"] = None
    if ds.compare and not ds.prev_daily.empty:
        prev_tot = ds.prev_daily.groupby("uid")["n"].sum()
        cur_u, prev_u = set(per_user.index), set(prev_tot.index)
        both = cur_u & prev_u
        pm = int(prev_tot.sum())
        out["compare"] = {
            "prev_messages": pm, "messages_change": (total_msgs / pm - 1) if pm else None,
            "prev_users": len(prev_u), "users_change": (U / len(prev_u) - 1) if prev_u else None,
            "retained": len(both), "new": len(cur_u - prev_u), "lost": len(prev_u - cur_u),
            "retention": (len(both) / len(prev_u)) if prev_u else None,
            "rel": make_rel(_lvl(D, 14, 28), ["«новый»/«ушёл» = писал/не писал, а не вступил/покинул сервер"]),
        }

    # Каналы
    out["channels"] = None
    ch = ds.channels
    if not ch.empty:
        t = (ch.groupby("channel_id")
               .agg(channel=("channel", "first"), messages=("n", "sum"), authors=("uid", "nunique"))
               .sort_values("messages", ascending=False))
        t["share"] = t["messages"] / t["messages"].sum()
        k_user = ch.groupby("uid")["channel_id"].nunique()
        out["channels"] = {
            "table": t, "top3_share": float(t["share"].values[:3].sum()),
            "hhi": float((t["share"].values ** 2).sum()),
            "single_channel_share": float((k_user == 1).mean()),
            "mean_channels": float(k_user.mean()),
            "rel": make_rel(_lvl(total_msgs, 300, 2000), []),
        }

    # Серверы (суммарный файл)
    out["servers"] = None
    if not ds.servers.empty:
        sv = ds.servers
        t = (sv.groupby("server").agg(messages=("n", "sum"), authors=("uid", "nunique"))
               .sort_values("messages", ascending=False))
        t["share"] = t["messages"] / t["messages"].sum()
        multi = int((sv.groupby("uid")["server"].nunique() > 1).sum())
        out["servers"] = {"table": t, "multi_server_users": multi,
                          "multi_server_share": multi / sv["uid"].nunique()}

    # Администрация
    out["staff"] = None
    if not ds.staff.empty:
        sm = int(ds.staff["n"].sum())
        out["staff"] = {
            "people": int(ds.staff["uid"].nunique()), "messages": sm,
            "share": sm / total_msgs if total_msgs else 0.0,
            "by_kind": {k: int(v) for k, v in ds.staff.groupby("kind")["n"].sum().items()},
        }
    return out


# ---------- Личные метрики ----------

def user_metrics(ds: Dataset) -> pd.DataFrame:
    days = calendar_days(ds)
    D = len(days)
    daily = ds.daily
    if daily.empty or D == 0:
        return pd.DataFrame()

    pivot = (daily.pivot_table(index="uid", columns="date", values="n", aggfunc="sum", fill_value=0)
                  .reindex(columns=days, fill_value=0))
    vals = pivot.values.astype(np.int64)
    act = vals > 0
    uids = pivot.index
    U = len(uids)

    df = pd.DataFrame(index=uids)
    df.index.name = "uid"
    n = vals.sum(axis=1)
    ad = act.sum(axis=1)
    df["messages"] = n
    df["active_days"] = ad
    df["active_share"] = ad / D
    df["avg_per_active_day"] = n / np.maximum(ad, 1)
    df["max_day"] = vals.max(axis=1)

    first = np.argmax(act, axis=1)
    last = D - 1 - np.argmax(act[:, ::-1], axis=1)
    df["first_date"] = days[first].date
    df["last_date"] = days[last].date
    df["days_since_last"] = (D - 1) - last

    # Серии активных дней подряд
    cur = np.zeros(U, dtype=int)
    longest = np.zeros(U, dtype=int)
    for j in range(D):
        cur = np.where(act[:, j], cur + 1, 0)
        longest = np.maximum(longest, cur)
    df["longest_streak"] = longest
    df["current_streak"] = cur

    # Постоянство по неделям (недели с понедельника)
    codes = (np.asarray((days - days[0]).days) + days[0].weekday()) // 7
    W = int(codes.max()) + 1
    wk = np.zeros(U, dtype=int)
    for w in range(W):
        wk += act[:, codes == w].any(axis=1)
    df["weeks_active"] = wk
    df["weeks_share"] = wk / W

    # Тренд: вторая половина окна против первой (в расчёте на день)
    if D >= MIN_TREND_DAYS:
        h = D // 2
        f = vals[:, :h].sum(axis=1).astype(float)
        s = vals[:, h:].sum(axis=1).astype(float)
        f_rate, s_rate = f / h, s / (D - h)
        ratio = np.where(f_rate > 0, s_rate / np.where(f_rate > 0, f_rate, 1.0), np.nan)
        trend = np.select(
            [(f == 0) & (s > 0), (f > 0) & (s == 0), ratio >= TREND_UP, ratio <= TREND_DOWN],
            ["новый в окне", "притих", "растёт", "снижается"], default="стабильно")
        trend = np.where(n < MIN_USER_MSGS_TREND, "мало данных", trend)
        df["trend_ratio"] = ratio
        df["trend"] = trend
    else:
        df["trend_ratio"] = np.nan
        df["trend"] = "н/д (короткое окно)"

    # Имена, роль, ответы
    info = ds.users.drop_duplicates("uid").set_index("uid")
    name = info["name"].reindex(uids).fillna("")
    df["name"] = np.where(name.values == "", uids.values, name.values)
    df["username"] = info["username"].reindex(uids).fillna("").values
    df["avatar"] = info["avatar"].reindex(uids).fillna("").values
    df["role"] = info["role"].reindex(uids).fillna("").values
    rep = info["replies"].reindex(uids).fillna(0).values.astype(int)
    df["replies"] = rep
    df["reply_share"] = rep / np.maximum(n, 1) if ds.full_data else np.nan
    df["is_staff"] = uids.isin(ds.staff["uid"]) if len(ds.staff) else False

    # Каналы
    for c in ("channels_used", "top_channel", "top_channel_share", "channel_entropy"):
        df[c] = np.nan if c != "top_channel" else ""
    ch = ds.channels[ds.channels["n"] > 0] if len(ds.channels) else ds.channels
    if len(ch):
        ch = ch.copy()
        ch["tot"] = ch.groupby("uid")["n"].transform("sum")
        ch["p"] = ch["n"] / ch["tot"]
        ch["plogp"] = -(ch["p"] * np.log(ch["p"]))
        k = ch.groupby("uid").size()
        ent = ch.groupby("uid")["plogp"].sum()
        norm = (ent / np.log(k.where(k > 1))).fillna(0.0)
        top = (ch.sort_values(["uid", "n"], ascending=[True, False])
                 .drop_duplicates("uid").set_index("uid"))
        df["channels_used"] = k.reindex(uids).values
        df["top_channel"] = top["channel"].reindex(uids).fillna("").values
        df["top_channel_share"] = top["p"].reindex(uids).values
        df["channel_entropy"] = norm.reindex(uids).values

    # Время суток и дни недели
    for c in ("peak_hour", "peak_weekday", "night_share", "weekend_share"):
        df[c] = np.nan
    ht = ds.heat
    if len(ht):
        ph = (ht.groupby(["uid", "hour"])["n"].sum().reset_index()
                .sort_values(["uid", "n"], ascending=[True, False]).drop_duplicates("uid").set_index("uid"))
        pw = (ht.groupby(["uid", "weekday"])["n"].sum().reset_index()
                .sort_values(["uid", "n"], ascending=[True, False]).drop_duplicates("uid").set_index("uid"))
        tot_u = ht.groupby("uid")["n"].sum()
        night = ht[ht["hour"] < NIGHT_HOURS].groupby("uid")["n"].sum()
        wkend = ht[ht["weekday"] >= 5].groupby("uid")["n"].sum()
        df["peak_hour"] = ph["hour"].reindex(uids).values
        df["peak_weekday"] = pw["weekday"].reindex(uids).values
        df["night_share"] = (night.reindex(uids).fillna(0) / tot_u.reindex(uids)).values
        df["weekend_share"] = (wkend.reindex(uids).fillna(0) / tot_u.reindex(uids)).values

    # Место на сервере
    total = float(n.sum())
    df["server_share"] = n / total if total else 0.0
    df["rank"] = df["messages"].rank(method="min", ascending=False).astype(int)
    df["percentile"] = df["messages"].rank(pct=True)

    # Достоверность личных выводов
    lv = np.where((n >= 50) & (ad >= 7), 2, np.where((n >= 10) & (ad >= 3), 1, 0))
    if D < MIN_TREND_DAYS:
        lv = np.minimum(lv, 1)
    if ds.incomplete or ds.truncated:
        lv = np.maximum(lv - 1, 0)
    df["reliability"] = [LEVELS[i] for i in lv]

    return df.sort_values(["messages", "name"], ascending=[False, True])