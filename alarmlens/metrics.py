"""Alarm-system performance metrics.

Targets below are paraphrased from the ISA-18.2 / EEMUA 191 performance-metric guidance as
commonly cited. They are approximate: check them against your own copy of the standard
and your site's alarm philosophy before relying on them.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class KPI:
    name: str
    value: float
    display: str
    target: str
    status: str  # "ok" | "warn" | "bad"


@dataclass
class Analysis:
    start: pd.Timestamp
    end: pd.Timestamp
    total_activations: int
    kpis: list
    per_10min: pd.Series
    top10: pd.DataFrame
    chattering: pd.DataFrame
    stale: pd.DataFrame
    priority_mix: pd.Series
    floods: pd.DataFrame
    response: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)


def _grade(value, ok_max, warn_max):
    if value <= ok_max:
        return "ok"
    if warn_max is not None and value <= warn_max:
        return "warn"
    return "bad"


def find_chattering(active, count=3, window_s=60):
    """Tags that activate `count` or more times within `window_s` seconds."""
    rows = []
    span = np.timedelta64(window_s, "s")
    for tag, g in active.groupby("tag"):
        t = g["time"].to_numpy()
        if len(t) < count:
            continue
        hits = (t[count - 1:] - t[: len(t) - count + 1]) <= span
        if hits.any():
            rows.append({"tag": tag, "message": g["message"].iloc[0], "bursts": int(hits.sum()),
                         "activations": len(t)})
    df = pd.DataFrame(rows, columns=["tag", "message", "bursts", "activations"])
    return df.sort_values("bursts", ascending=False, kind="stable").reset_index(drop=True)


def find_stale(df, end, hours=24):
    """Alarms whose last ACTIVE/CLEARED event is ACTIVE and older than `hours`."""
    ev = df[df["state"].isin(["ACTIVE", "CLEARED"])]
    last = ev.groupby("tag", sort=False).tail(1).set_index("tag")
    stale = last[(last["state"] == "ACTIVE") & ((end - last["time"]) >= pd.Timedelta(hours=hours))]
    out = stale[["message", "priority", "time"]].rename(columns={"time": "active_since"}).reset_index()
    out["hours_active"] = ((end - out["active_since"]).dt.total_seconds() / 3600).round(1)
    return out.sort_values("hours_active", ascending=False, kind="stable").reset_index(drop=True)


def find_floods(per_10min, threshold=10):
    """Group consecutive over-threshold 10-minute windows into flood episodes."""
    over = per_10min > threshold
    episodes, cur = [], None
    for ts, is_over in over.items():
        if is_over:
            if cur is None:
                cur = {"start": ts, "windows": 0, "alarms": 0, "peak": 0}
            cur["windows"] += 1
            cur["alarms"] += int(per_10min[ts])
            cur["peak"] = max(cur["peak"], int(per_10min[ts]))
        elif cur is not None:
            episodes.append(cur)
            cur = None
    if cur is not None:
        episodes.append(cur)
    df = pd.DataFrame(episodes, columns=["start", "windows", "alarms", "peak"])
    df["minutes"] = df["windows"] * 10
    return df


def operator_response(df):
    """Time from each activation to the next acknowledgement of the same tag.

    An acknowledgement only counts if it comes before that tag's next activation.
    Returns a dict with overall stats and a per-tag table of the slowest responses.
    """
    act = df[df["state"] == "ACTIVE"][["time", "tag", "message"]].sort_values("time", kind="stable")
    ack = df[df["state"] == "ACK"][["time", "tag"]].sort_values("time", kind="stable")
    empty = {"has_acks": False, "median_s": None, "p90_s": None, "unacked_pct": None,
             "slowest": pd.DataFrame(columns=["tag", "message", "median_min", "unacked", "activations"])}
    if act.empty or ack.empty:
        return empty
    act = act.reset_index(drop=True)
    act["next_active"] = act.groupby("tag")["time"].shift(-1)
    m = pd.merge_asof(act, ack.rename(columns={"time": "ack_time"}), left_on="time", right_on="ack_time",
                      by="tag", direction="forward")
    late = m["next_active"].notna() & (m["ack_time"] >= m["next_active"])
    m.loc[late, "ack_time"] = pd.NaT
    m["ack_s"] = (m["ack_time"] - m["time"]).dt.total_seconds()
    acked = m["ack_s"].dropna()
    per_tag = (m.groupby("tag")
               .agg(message=("message", "first"), median_s=("ack_s", "median"),
                    unacked=("ack_s", lambda x: int(x.isna().sum())), activations=("ack_s", "size"))
               .reset_index())
    per_tag["median_min"] = (per_tag["median_s"] / 60).round(1)
    slowest = (per_tag.sort_values(["median_s", "unacked"], ascending=False, na_position="first", kind="stable")
               .head(10)[["tag", "message", "median_min", "unacked", "activations"]].reset_index(drop=True))
    return {"has_acks": True,
            "median_s": float(acked.median()) if len(acked) else None,
            "p90_s": float(acked.quantile(0.9)) if len(acked) else None,
            "unacked_pct": float(m["ack_s"].isna().mean() * 100),
            "slowest": slowest}


def analyze(df, flood_threshold=10, chatter_count=3, chatter_window_s=60, stale_hours=24):
    if df.empty:
        raise ValueError("The alarm log has no usable rows.")
    start, end = df["time"].min(), df["time"].max()
    active = df[df["state"] == "ACTIVE"]
    n = len(active)
    if n == 0:
        raise ValueError("No alarm activations found. Check the state column values "
                         "(expected words like Active/Raised/Came In).")

    first_bin = start.floor("10min")
    index = pd.date_range(first_bin, end.floor("10min"), freq="10min")
    per_10 = active.groupby(active["time"].dt.floor("10min")).size().reindex(index, fill_value=0)
    hours = max(len(index) / 6, 1 / 6)
    per_day = n / hours * 24
    avg_10 = float(per_10.mean())
    peak_10 = int(per_10.max())
    flood_pct = float((per_10 > flood_threshold).mean() * 100)

    counts = (active.groupby("tag")
              .agg(count=("tag", "size"), message=("message", "first"), priority=("priority", "first"))
              .sort_values("count", ascending=False, kind="stable"))
    top10 = counts.head(10).reset_index()
    top10["share_pct"] = (top10["count"] / n * 100).round(1)
    top10_share = float(top10["count"].sum() / n * 100)

    chattering = find_chattering(active, chatter_count, chatter_window_s)
    stale = find_stale(df, end, stale_hours)
    floods = find_floods(per_10, flood_threshold)

    mix = active["priority"].value_counts(normalize=True).mul(100).round(1)
    mix = mix.reindex([p for p in ["High", "Medium", "Low", "Unmapped"] if p in mix.index])
    high_pct = float(mix.get("High", 0.0))

    kpis = [
        KPI("Alarms per day", per_day, f"{per_day:,.0f}",
            "~150 very likely acceptable · ~300 maximum manageable", _grade(per_day, 150, 300)),
        KPI("Average per 10 min", avg_10, f"{avg_10:.2f}",
            "~1 very likely acceptable · ~2 maximum manageable", _grade(avg_10, 1, 2)),
        KPI("Time in flood", flood_pct, f"{flood_pct:.1f}%",
            f"< ~1% of 10-min periods over {flood_threshold} alarms", _grade(flood_pct, 1, 5)),
        KPI("Peak in 10 min", peak_10, f"{peak_10}",
            f"≤ {flood_threshold}", _grade(peak_10, flood_threshold, None)),
        KPI("Top-10 share of load", top10_share, f"{top10_share:.1f}%",
            "~1–5% maximum", _grade(top10_share, 1, 5)),
        KPI("Chattering alarms", len(chattering), f"{len(chattering)}",
            f"0 (≥{chatter_count} activations in {chatter_window_s}s)", _grade(len(chattering), 0, None)),
        KPI("Stale alarms", len(stale), f"{len(stale)}",
            f"< 5 active longer than {stale_hours}h", _grade(len(stale), 4, None)),
        KPI("High-priority share", high_pct, f"{high_pct:.1f}%",
            "~5% (typical mix ~80% low / 15% medium / 5% high)", _grade(high_pct, 7, 15)),
    ]
    return Analysis(start, end, n, kpis, per_10, top10, chattering, stale, mix, floods,
                    response=operator_response(df),
                    settings={"distinct_tags": int(active["tag"].nunique()),
                              "flood_threshold": flood_threshold, "chatter_count": chatter_count,
                              "chatter_window_s": chatter_window_s, "stale_hours": stale_hours})
