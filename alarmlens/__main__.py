"""Command line:  python -m alarmlens ALARM_LOG.csv [-o report.html] [--no-ai]"""
import argparse
import os
import sys
import webbrowser

from .ai import ai_summary, rule_recommendations
from .load import load_alarm_log, parse_priority_map
from .metrics import analyze
from .report import render

ICON = {"ok": "OK  ", "warn": "WARN", "bad": "BAD "}


def main(argv=None):
    p = argparse.ArgumentParser(prog="alarmlens", description="Analyze a SCADA alarm log CSV.")
    p.add_argument("csv", help="alarm log export (CSV)")
    p.add_argument("-o", "--output", default="alarmlens_report.html", help="HTML report path")
    p.add_argument("--no-ai", action="store_true", help="skip the local AI summary")
    p.add_argument("--model", default="llama3.2", help="Ollama model (default llama3.2)")
    p.add_argument("--open", action="store_true", help="open the report in your browser")
    p.add_argument("--sample", action="store_true", help="label the report as sample data")
    p.add_argument("--flood-threshold", type=int, default=10)
    p.add_argument("--stale-hours", type=float, default=24)
    p.add_argument("--priority-map", help='e.g. "1=High,2=Medium,3=Low"')
    for f in ("time", "tag", "message", "priority", "state"):
        p.add_argument(f"--col-{f}", help=f"name of the {f} column, if not auto-detected")
    args = p.parse_args(argv)

    colmap = {f: getattr(args, f"col_{f}") for f in ("time", "tag", "message", "priority", "state")
              if getattr(args, f"col_{f}")}
    try:
        df = load_alarm_log(args.csv, colmap, parse_priority_map(args.priority_map))
        a = analyze(df, flood_threshold=args.flood_threshold, stale_hours=args.stale_hours)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"\nAlarmLens · {a.total_activations:,} activations · {a.start:%Y-%m-%d} → {a.end:%Y-%m-%d}\n")
    for k in a.kpis:
        print(f"  [{ICON[k.status]}] {k.name:<22} {k.display:>9}   target: {k.target}")
    recs = rule_recommendations(a)
    ai_text, note = (None, "AI summary skipped (--no-ai).")
    if not args.no_ai:
        print("\nAsking the local AI for a summary (Ollama)...")
        ai_text, note = ai_summary(a, model=args.model)
        if note:
            print("  " + note)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(render(a, recs, ai_text, note, os.path.basename(args.csv), args.sample))
    print(f"\nReport written: {os.path.abspath(args.output)}")
    if args.open:
        webbrowser.open("file://" + os.path.abspath(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
