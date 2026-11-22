"""Recommendations: rule-based ones always, plus an optional AI-written summary
from a free local model through Ollama (https://ollama.com). Nothing leaves the PC."""
import json
import urllib.error
import urllib.request


def rule_recommendations(a):
    recs = []
    k = {kpi.name: kpi for kpi in a.kpis}
    if not a.chattering.empty:
        tags = ", ".join(a.chattering["tag"].head(3))
        recs.append(f"Fix chattering alarms first ({tags}). Review deadband, on-delay/off-delay "
                    "timers, or the sensor itself. These are usually the cheapest load reduction.")
    if k["Top-10 share of load"].status != "ok":
        top = a.top10.iloc[0]
        recs.append(f"Rationalize the bad actors: the top 10 tags produce "
                    f"{k['Top-10 share of load'].display} of all alarms. Start with {top['tag']} "
                    f"({int(top['count'])} activations). Confirm each one needs an operator action.")
        if a.settings.get("distinct_tags", 0) < 100:
            recs[-1] += (f" Note: only {a.settings['distinct_tags']} different tags alarmed in this log. "
                         "The 1–5% benchmark assumes a large system, so a high top-10 share is expected here.")
    if not a.floods.empty:
        f = a.floods.sort_values("alarms", ascending=False).iloc[0]
        recs.append(f"Investigate the {len(a.floods)} flood episode(s). The largest started "
                    f"{f['start']:%d %b %H:%M} with {int(f['alarms'])} alarms. Consider "
                    "state-based suppression or first-out logic for that upset.")
    if not a.stale.empty:
        recs.append(f"Review {len(a.stale)} stale alarm(s), active more than "
                    f"{a.settings['stale_hours']}h. Either the condition needs fixing or the alarm "
                    "should be shelved through a controlled, documented process.")
    r = a.response
    if r.get("has_acks") and r["unacked_pct"] and r["unacked_pct"] > 5:
        recs.append(f"{r['unacked_pct']:.0f}% of alarms were never acknowledged. Review the slowest-to-acknowledge "
                    "tags. If operators routinely ignore an alarm, it may not need to be an alarm.")
    if k["High-priority share"].status != "ok":
        recs.append("Re-check priority assignment. Too many high-priority alarms dilute the ones "
                    "that matter. Base priority on consequence severity and time to respond.")
    if k["Alarms per day"].status == "ok" and not recs:
        recs.append("The alarm system is performing within the benchmark ranges. Keep monitoring.")
    recs.append("Any change to alarm settings in a GMP system goes through change control "
                "and is assessed for validation impact.")
    return recs


def build_prompt(a):
    lines = [f"- {k.name}: {k.display} (benchmark: {k.target}; status {k.status})" for k in a.kpis]
    top = "\n".join(f"- {row['tag']}: {row['count']} activations ({row['share_pct']}%) — {row['message']}"
                    for _, row in a.top10.head(5).iterrows())
    chat = ", ".join(a.chattering["tag"].head(5)) or "none"
    return (
        "You are an experienced alarm-management engineer in GMP pharmaceutical manufacturing. "
        "Write a short alarm-performance summary for a plant automation team (max 180 words): "
        "first one sentence on overall health, then 3 prioritized actions. Be specific, use the "
        "tag names, and do not invent data that is not given.\n\n"
        f"Period: {a.start:%Y-%m-%d %H:%M} to {a.end:%Y-%m-%d %H:%M}, {a.total_activations} alarm activations.\n"
        "KPIs:\n" + "\n".join(lines) + "\n\nTop alarms:\n" + top +
        f"\n\nChattering tags: {chat}\nFlood episodes: {len(a.floods)}\nStale alarms: {len(a.stale)}"
    )


def ai_summary(a, model="llama3.2", url="http://localhost:11434", timeout=180):
    """Returns (text, error). Error is a readable message if Ollama isn't available."""
    body = json.dumps({"model": model, "prompt": build_prompt(a), "stream": False}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        if "error" in data:
            return None, f"Ollama error: {data['error']}"
        return data.get("response", "").strip(), None
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, f"AI summary skipped: Ollama not reachable at {url} ({e.__class__.__name__})."
