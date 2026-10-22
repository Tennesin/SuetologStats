"""Этап 3: СКП (значимость пользователя для сервера) и справочная шкала «риск потери»."""

import numpy as np
import pandas as pd

import settings as S
from loader import Dataset
from metrics import calendar_days


def _label(value: float, levels) -> str:
    for threshold, name in levels:
        if value >= threshold:
            return name
    return levels[-1][1]


def compute_skp(ds: Dataset, um: pd.DataFrame,
                top_n: int = S.SELECT_TOP_N, min_skp: float = S.SELECT_MIN_SKP) -> pd.DataFrame:
    """Возвращает таблицу с индексом uid (как у user_metrics), отсортированную по СКП."""
    if um.empty:
        return pd.DataFrame()
    idx = um.index
    n = um["messages"].astype(float)
    nan = pd.Series(np.nan, index=idx)

    # V — вклад
    p95 = float(np.percentile(n, S.SKP_V_PERCENTILE))
    V = (np.log1p(n) / np.log1p(p95)).clip(upper=1.0)

    # C — постоянство
    C = S.SKP_C_DAYS_W * um["active_share"] + (1 - S.SKP_C_DAYS_W) * um["weeks_share"]

    # R — охват и D — зависимость сервера (нужны данные по каналам)
    R, Dd = nan.copy(), nan.copy()
    ch = ds.channels[ds.channels["n"] > 0]
    if len(ch):
        chan_tot = ch.groupby("channel_id")["n"].sum()
        sig = chan_tot[chan_tot / chan_tot.sum() >= S.SKP_SIG_CHANNEL].index
        denom = max(1, min(S.SKP_R_CAP, len(sig)))
        cnt = ch[ch["n"] >= S.SKP_R_MIN_MSGS].groupby("uid").size()
        R = (cnt.reindex(idx).fillna(0) / denom).clip(upper=1.0)
        s = ch[ch["channel_id"].isin(sig)].copy()
        s["share"] = s["n"] / s["channel_id"].map(chan_tot)
        Dd = (s.groupby("uid")["share"].max().reindex(idx).fillna(0) / S.SKP_D_CEIL).clip(upper=1.0)

    # I — взаимодействие (только ответы; сглаживание к среднему по серверу)
    if ds.full_data and n.sum() > 0:
        m = float(um["replies"].sum()) / float(n.sum())
        rep = um["replies"].astype(float)
        I = (((rep + S.SKP_I_PRIOR * m) / (n + S.SKP_I_PRIOR)) / S.SKP_I_CEIL).clip(upper=1.0)
    else:
        I = nan.copy()

    # P — роль
    P = pd.Series(0.0, index=idx)
    if len(ds.staff):
        kind_w = ds.staff["kind"].map(S.SKP_ROLE)
        best = kind_w.groupby(ds.staff["uid"]).max()
        P = best.reindex(idx).fillna(0.0)

    comps = pd.DataFrame({"V": V, "C": C, "R": R, "I": I, "D": Dd, "P": P}, index=idx)
    w = pd.Series(S.SKP_WEIGHTS)[list(comps.columns)]
    avail = comps.notna()
    # если компонента нет (старый формат файла), его вес перераспределяется на остальные
    skp = (comps.fillna(0.0) * w).sum(axis=1) / (avail * w).sum(axis=1) * 100

    # Риск потери
    days_n = len(calendar_days(ds))
    ad = um["active_days"].clip(lower=1)
    expected_gap = (days_n / ad).clip(lower=1.0)
    recency = ((um["days_since_last"] / expected_gap - 1.0) / S.RISK_RECENCY_GAPS).clip(0.0, 1.0)

    ratio = um["trend_ratio"]
    decline = ((1.0 - ratio) / S.RISK_DECLINE_RANGE).clip(0.0, 1.0)
    is_new = ratio.isna() & ~um["trend"].astype(str).str.startswith("н/д")
    decline = decline.mask(is_new, 0.0)       # «новый в окне» — не падение

    streak = pd.Series(
        np.where(um["current_streak"] > 0, 0.0,
                 np.minimum(1.0, um["longest_streak"] / S.RISK_STREAK_DAYS)),
        index=idx)

    rc = pd.DataFrame({"recency": recency, "decline": decline, "streak": streak}, index=idx)
    rw = pd.Series(S.RISK_WEIGHTS)[list(rc.columns)]
    ravail = rc.notna()
    risk = (rc.fillna(0.0) * rw).sum(axis=1) / (ravail * rw).sum(axis=1) * 100

    out = comps.copy()
    out["skp"] = skp
    out["skp_partial"] = ~avail.all(axis=1)
    out["skp_level"] = skp.map(lambda v: _label(v, S.SKP_LEVELS))
    out["skp_rank"] = skp.rank(method="min", ascending=False).astype(int)
    out["risk"] = risk
    out["risk_level"] = risk.map(lambda v: _label(v, S.RISK_LEVELS))
    out["risk_recency"] = recency
    out["risk_decline"] = decline
    out["risk_streak"] = streak

    out = out.sort_values("skp", ascending=False, kind="stable")
    order = out["skp"].rank(method="first", ascending=False)
    out["selected"] = (order <= top_n) | (out["skp"] >= min_skp)
    return out