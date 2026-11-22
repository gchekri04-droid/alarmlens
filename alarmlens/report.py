"""Self-contained HTML report (no internet needed to open it)."""
import html

STATUS_LABEL = {"ok": "Within benchmark", "warn": "Watch", "bad": "Action needed"}


def _e(x):
    return html.escape(str(x))


def _chart(per_10, threshold, width=900, height=200):
    """Bar chart of alarms per 10 minutes with the flood threshold line."""
    pad_l, pad_b, pad_t = 34, 22, 10
    w, h = width - pad_l - 8, height - pad_b - pad_t
    n = len(per_10)
    ymax = max(int(per_10.max()), threshold + 2)
    bw = w / n
    bars = []
    for i, v in enumerate(per_10.values):
        if v == 0:
            continue
        bh = v / ymax * h
        cls = "flood" if v > threshold else "bar"
        bars.append(f'<rect class="{cls}" x="{pad_l + i * bw:.2f}" y="{pad_t + h - bh:.2f}" '
                    f'width="{max(bw, 0.8):.2f}" height="{bh:.2f}"/>')
    ty = pad_t + h - threshold / ymax * h
    ticks = []
    for v in sorted({0, threshold, ymax}):
        y = pad_t + h - v / ymax * h
        ticks.append(f'<text class="ax" x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end">{v}</text>')
    days = []
    for i, ts in enumerate(per_10.index):
        x = pad_l + i * bw
        if ts.hour == 0 and ts.minute == 0 and x + 45 < width:
            days.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{pad_t}" y2="{pad_t + h}"/>'
                        f'<text class="ax" x="{x + 3:.1f}" y="{height - 6}">{ts:%a %d}</text>')
    return (f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Alarms per 10 minutes">'
            + "".join(days) + "".join(bars)
            + f'<line class="thr" x1="{pad_l}" x2="{width - 8}" y1="{ty:.1f}" y2="{ty:.1f}"/>'
            + f'<text class="thr-l" x="{width - 10}" y="{ty - 5:.1f}" text-anchor="end">flood threshold ({threshold})</text>'
            + "".join(ticks) + "</svg>")


def _table(df, cols, headers):
    if df.empty:
        return '<p class="none">None found.</p>'
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if hasattr(v, "strftime"):
                v = v.strftime("%d %b %H:%M")
            cells.append(f"<td>{_e(v)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def _mins(sec):
    return "–" if sec is None else (f"{sec:.0f} s" if sec < 120 else f"{sec / 60:.1f} min")


def _response_section(r):
    if not r.get("has_acks"):
        return ('<section><h2>Operator response</h2><p class="none">No acknowledgement events in this log, '
                'so response times can\'t be measured.</p></section>')
    stats = (f'<ul class="mix"><li><span>Median time to acknowledge</span><b>{_mins(r["median_s"])}</b></li>'
             f'<li><span>90% acknowledged within</span><b>{_mins(r["p90_s"])}</b></li>'
             f'<li><span>Never acknowledged</span><b>{r["unacked_pct"]:.1f}%</b></li></ul>')
    note = ('<p class="none" style="margin-top:10px">Slow or missing acknowledgements often point to alarms '
            'operators have learned to ignore. Those are good rationalization candidates.</p>')
    table = _table(r["slowest"], ["tag", "median_min", "unacked", "activations"],
                   ["Tag", "Median min to ack", "Never acked", "Activations"])
    return (f'<div class="two"><section><h2>Operator response</h2>{stats}{note}</section>'
            f'<section><h2>Slowest to acknowledge</h2>{table}</section></div>')


def render(a, recommendations, ai_text=None, ai_note=None, source_name="alarm log", sample=False):
    kpis = "".join(
        f'<div class="kpi {k.status}"><span class="kn">{_e(k.name)}</span><b>{_e(k.display)}</b>'
        f'<span class="st">{STATUS_LABEL[k.status]}</span><span class="tg">{_e(k.target)}</span></div>'
        for k in a.kpis)
    mix = "".join(f"<li><span>{_e(p)}</span><b>{v}%</b></li>" for p, v in a.priority_mix.items())
    recs = "".join(f"<li>{_e(r)}</li>" for r in recommendations)
    if ai_text:
        ai = f'<div class="ai"><p class="lbl">AI summary · local model, review before use</p><p>{_e(ai_text).replace(chr(10), "<br>")}</p></div>'
    else:
        ai = f'<p class="none">{_e(ai_note or "AI summary not requested.")}</p>'
    banner = ('<p class="sample">Sample data: a fictional filling line generated for demonstration. '
              'Not from any real plant.</p>') if sample else ""
    floods = a.floods.copy()
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AlarmLens Report</title>
<style>
:root{{--bg:#f5f7fa;--card:#fff;--line:#d9e0ea;--fg:#14202e;--mu:#5b6b80;--ac:#0a7e93;--ok:#1a7f4b;--warn:#a86400;--bad:#c2362b;
--okb:#e3f4ea;--warnb:#fdf0dc;--badb:#fbe5e3;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1420;--card:#141e2e;--line:#26354d;--fg:#e3e9f1;--mu:#8fa0b8;--ac:#2ec9e3;
--ok:#4cc985;--warn:#f0b04e;--bad:#f07468;--okb:#13301f;--warnb:#3a2a10;--badb:#3d1917;color-scheme:dark}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 "Segoe UI",system-ui,sans-serif}}
.w{{max-width:1000px;margin:0 auto;padding:28px 18px 48px;display:grid;gap:28px}}
h1{{margin:0;font-size:1.7rem}}h2{{margin:0 0 12px;font-size:1.1rem}}
.meta{{color:var(--mu);font-size:.9rem}}.sample{{background:var(--warnb);color:var(--warn);padding:8px 12px;border-radius:8px;margin:10px 0 0;font-size:.9rem}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--ok);border-radius:8px;padding:12px 14px;display:grid;gap:2px}}
.kpi.warn{{border-left-color:var(--warn)}}.kpi.bad{{border-left-color:var(--bad)}}
.kn{{font-size:.82rem;color:var(--mu)}}.kpi b{{font-size:1.5rem;font-variant-numeric:tabular-nums}}
.st{{font-size:.75rem;font-weight:600;color:var(--ok)}}.warn .st{{color:var(--warn)}}.bad .st{{color:var(--bad)}}
.tg{{font-size:.75rem;color:var(--mu)}}
section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
svg{{width:100%;height:auto;display:block}}.bar{{fill:var(--ac)}}.flood{{fill:var(--bad)}}
.thr{{stroke:var(--bad);stroke-dasharray:5 4}}.thr-l{{fill:var(--bad);font-size:11px}}.ax{{fill:var(--mu);font-size:11px}}.grid{{stroke:var(--line)}}
.tw{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:.9rem}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}}th{{color:var(--mu);font-weight:600}}
td{{font-variant-numeric:tabular-nums}}.none{{color:var(--mu);margin:0}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}@media(max-width:700px){{.two{{grid-template-columns:1fr}}}}
.mix{{list-style:none;padding:0;margin:0;display:grid;gap:6px}}.mix li{{display:flex;justify-content:space-between}}
ol.recs{{margin:0;padding-left:20px;display:grid;gap:8px}}.ai{{background:var(--bg);border-radius:8px;padding:12px 14px;margin-top:14px}}
.lbl{{font-size:.75rem;color:var(--mu);margin:0 0 6px;text-transform:uppercase;letter-spacing:.06em}}.ai p{{margin:0}}
footer{{color:var(--mu);font-size:.8rem}}
</style></head><body><div class="w">
<header><h1>AlarmLens Report</h1>
<p class="meta">{_e(source_name)} · {a.start:%d %b %Y %H:%M} → {a.end:%d %b %Y %H:%M} · {a.total_activations:,} alarm activations</p>{banner}</header>
<div class="kpis">{kpis}</div>
<section><h2>Alarms per 10 minutes</h2>{_chart(a.per_10min, a.settings["flood_threshold"])}</section>
<section><h2>Recommended actions</h2><ol class="recs">{recs}</ol>{ai}</section>
{_response_section(a.response)}
<section><h2>Top 10 bad actors</h2>{_table(a.top10, ["tag","message","priority","count","share_pct"], ["Tag","Message","Priority","Activations","% of load"])}</section>
<div class="two">
<section><h2>Chattering alarms</h2>{_table(a.chattering, ["tag","bursts","activations"], ["Tag","Bursts","Activations"])}</section>
<section><h2>Priority mix</h2><ul class="mix">{mix}</ul></section>
</div>
<div class="two">
<section><h2>Flood episodes</h2>{_table(floods, ["start","minutes","alarms","peak"], ["Start","Minutes","Alarms","Peak / 10 min"])}</section>
<section><h2>Stale alarms</h2>{_table(a.stale, ["tag","active_since","hours_active"], ["Tag","Active since","Hours"])}</section>
</div>
<footer>Benchmarks are approximate, paraphrased from commonly cited ISA-18.2 / EEMUA 191 guidance. Confirm against the standard and your site alarm philosophy. Generated by AlarmLens.</footer>
</div></body></html>"""
