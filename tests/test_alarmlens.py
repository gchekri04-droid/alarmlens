import io

import pandas as pd
import pytest

from alarmlens.ai import rule_recommendations
from alarmlens.load import load_alarm_log, normalize_state, parse_priority_map
from alarmlens.metrics import analyze
from alarmlens.report import render


def csv(rows, header="Timestamp,Tag,Message,Priority,State"):
    return io.StringIO(header + "\n" + "\n".join(rows))


def test_state_words():
    assert normalize_state("Came In") == "ACTIVE"
    assert normalize_state("RAISED") == "ACTIVE"
    assert normalize_state("Went Out") == "CLEARED"
    assert normalize_state("Acknowledged") == "ACK"
    assert normalize_state("whatever") == "OTHER"


def test_column_autodetect_and_override():
    df = load_alarm_log(csv(["2026-01-01 00:00:00,T1,msg,High,Active"],
                            header="Raise Time,Source,Text,Severity,Event"),
                        column_map={"time": "Raise Time"})
    assert list(df.columns) == ["time", "tag", "message", "priority", "state"]
    assert df.loc[0, "state"] == "ACTIVE" and df.loc[0, "priority"] == "High"


def test_missing_column_gives_clear_error():
    with pytest.raises(ValueError, match="state"):
        load_alarm_log(csv(["2026-01-01 00:00:00,T1"], header="Timestamp,Tag"))


def test_numeric_priority_map():
    df = load_alarm_log(csv(["2026-01-01 00:00:00,T1,m,1,Active"]), priority_map=parse_priority_map("1=high,2=Low"))
    assert df.loc[0, "priority"] == "High"


def test_flood_chatter_stale_counts():
    rows = []
    # flood: 12 activations of different tags inside one 10-min window
    for i in range(12):
        rows.append(f"2026-01-01 01:00:{i*4:02d},F{i},flood,Low,Came In")
        rows.append(f"2026-01-01 01:30:{i*4:02d},F{i},flood,Low,Went Out")
    # chattering: C1 three times in 20 s
    for s in (0, 10, 20):
        rows.append(f"2026-01-01 03:00:{s:02d},C1,chat,Low,Came In")
        rows.append(f"2026-01-01 03:00:{s + 2:02d},C1,chat,Low,Went Out")
    # stale: S1 active and never cleared, 30 h before the end of the log
    rows.append("2026-01-01 00:00:00,S1,stale,High,Came In")
    # cleared alarm is not stale
    rows.append("2026-01-01 00:00:00,OK1,fine,Low,Came In")
    rows.append("2026-01-01 00:05:00,OK1,fine,Low,Went Out")
    rows.append("2026-01-02 06:00:00,END,end,Low,Came In")
    a = analyze(load_alarm_log(csv(rows)))
    k = {x.name: x for x in a.kpis}
    assert a.total_activations == 12 + 3 + 1 + 1 + 1
    assert k["Peak in 10 min"].value == 12 and k["Peak in 10 min"].status == "bad"
    assert len(a.floods) == 1 and a.floods.loc[0, "alarms"] == 12
    assert list(a.chattering["tag"]) == ["C1"]
    assert list(a.stale["tag"]) == ["S1"]
    assert a.stale.loc[0, "hours_active"] == 30.0


def test_quiet_system_is_ok_and_report_renders():
    rows = [f"2026-01-01 {h:02d}:00:00,T{h % 3},m,Low,Came In" for h in range(24)]
    a = analyze(load_alarm_log(csv(rows)))
    k = {x.name: x for x in a.kpis}
    assert k["Alarms per day"].status == "ok"
    assert k["Chattering alarms"].value == 0
    html = render(a, rule_recommendations(a), sample=True)
    assert "AlarmLens Report" in html and "Sample data" in html


def test_no_activations_raises():
    with pytest.raises(ValueError, match="No alarm activations"):
        analyze(load_alarm_log(csv(["2026-01-01 00:00:00,T1,m,Low,Went Out"])))


def test_html_escapes_tag_text():
    a = analyze(load_alarm_log(csv(["2026-01-01 00:00:00,<script>,x,Low,Came In"])))
    assert "<script>" not in render(a, [])


def test_operator_response_times():
    rows = [
        "2026-01-01 00:00:00,A,a,Low,Came In",
        "2026-01-01 00:01:00,A,a,Low,Acknowledged",      # 60 s
        "2026-01-01 00:10:00,A,a,Low,Came In",
        "2026-01-01 00:20:00,A,a,Low,Came In",           # previous never acked before this one
        "2026-01-01 00:23:00,A,a,Low,Acknowledged",      # 180 s for the third
        "2026-01-01 01:00:00,B,b,Low,Came In",           # never acked
    ]
    r = analyze(load_alarm_log(csv(rows))).response
    assert r["has_acks"]
    assert r["median_s"] == 120.0
    assert round(r["unacked_pct"], 1) == 50.0
    assert r["slowest"].iloc[0]["tag"] == "B"


def test_no_acks_is_handled():
    a = analyze(load_alarm_log(csv(["2026-01-01 00:00:00,T1,m,Low,Came In"])))
    assert a.response["has_acks"] is False
    assert "can't be measured" in render(a, [])
