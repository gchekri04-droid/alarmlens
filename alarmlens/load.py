"""Load an alarm-log CSV export and normalize it to columns: time, tag, message, priority, state.

SCADA systems name their export columns differently, so common names are auto-detected.
Override any of them with column_map, e.g. {"time": "Raise Time", "tag": "Source"}.
"""
import pandas as pd

ALIASES = {
    "time": ["timestamp", "time", "datetime", "date/time", "date time", "event time", "raise time", "time stamp"],
    "tag": ["tag", "source", "alarm tag", "tag name", "alarm name", "name", "object", "alarm source"],
    "message": ["message", "text", "alarm text", "alarm message", "description", "event text"],
    "priority": ["priority", "severity", "alarm class", "class", "alarm priority"],
    "state": ["state", "event", "status", "event type", "alarm state", "transition"],
}

ACTIVE_WORDS = {"active", "raised", "came in", "come in", "incoming", "in", "alarm", "on", "set"}
CLEARED_WORDS = {"cleared", "clear", "went out", "gone", "outgoing", "out", "normal", "rtn",
                 "return to normal", "off", "reset", "inactive"}
ACK_WORDS = {"ack", "acked", "acknowledged", "acknowledge"}


def _find(columns, wanted):
    lower = {c.strip().lower(): c for c in columns}
    for alias in ALIASES[wanted]:
        if alias in lower:
            return lower[alias]
    return None


def normalize_state(value):
    v = str(value).strip().lower()
    if v in ACTIVE_WORDS:
        return "ACTIVE"
    if v in CLEARED_WORDS:
        return "CLEARED"
    if v in ACK_WORDS or v.startswith("ack"):
        return "ACK"
    return "OTHER"


def normalize_priority(value, priority_map=None):
    v = str(value).strip()
    if priority_map and v in priority_map:
        return priority_map[v]
    low = v.lower()
    if any(w in low for w in ("crit", "urgent", "high", "emergency")):
        return "High"
    if "med" in low:
        return "Medium"
    if "low" in low:
        return "Low"
    return "Unmapped"


def parse_priority_map(text):
    """'1=High,2=Medium,3=Low' -> {'1': 'High', ...}"""
    if not text:
        return None
    out = {}
    for part in text.split(","):
        key, _, val = part.partition("=")
        out[key.strip()] = val.strip().capitalize()
    return out


def load_alarm_log(path_or_buffer, column_map=None, priority_map=None):
    raw = pd.read_csv(path_or_buffer)
    column_map = dict(column_map or {})
    cols = {}
    for field in ("time", "tag", "message", "priority", "state"):
        src = column_map.get(field) or _find(raw.columns, field)
        if src is None and field in ("time", "tag", "state"):
            raise ValueError(
                f"Couldn't find a '{field}' column. Columns in the file: {list(raw.columns)}. "
                f"Tell AlarmLens which one to use, e.g. --col-{field} \"Column Name\".")
        cols[field] = src

    df = pd.DataFrame({
        "time": pd.to_datetime(raw[cols["time"]], errors="coerce"),
        "tag": raw[cols["tag"]].astype(str).str.strip(),
        "message": raw[cols["message"]].astype(str) if cols["message"] else "",
        "priority": (raw[cols["priority"]].map(lambda v: normalize_priority(v, priority_map))
                     if cols["priority"] else "Unmapped"),
        "state": raw[cols["state"]].map(normalize_state),
    })
    bad = df["time"].isna().sum()
    df = df.dropna(subset=["time"]).sort_values("time", kind="stable").reset_index(drop=True)
    df.attrs["dropped_rows"] = int(bad)
    return df
