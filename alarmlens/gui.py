"""AlarmLens window: drop (or choose) an alarm-log CSV, click Analyze, open the report.

Run:  python -m alarmlens.gui
Drag-and-drop uses the optional 'tkinterdnd2' package; without it, use the Choose button.
"""
import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog

from .ai import ai_summary, rule_recommendations
from .load import load_alarm_log
from .metrics import analyze
from .report import render

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # not installed, or Tk extension missing
    TkinterDnD = None

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(HERE, "sample", "alarm_log_sample.csv")

BG, PANEL, LINE, FG, MUTED, ACCENT = "#0d1420", "#141e2e", "#26354d", "#e3e9f1", "#8fa0b8", "#2ec9e3"
STATUS_COLOR = {"ok": "#4cc985", "warn": "#f0b04e", "bad": "#f07468"}
STATUS_TEXT = {"ok": "OK", "warn": "Watch", "bad": "Action"}


class AlarmLensApp:
    def __init__(self, root):
        self.root = root
        self.path = None
        self.report_path = None
        self.q = queue.Queue()
        root.title("AlarmLens")
        root.geometry("720x640")
        root.minsize(560, 520)
        root.configure(bg=BG)
        self._build()
        root.after(60, self._poll)

    # ---------- layout ----------
    def _build(self):
        f = ("Segoe UI", 10)
        tk.Label(self.root, text="AlarmLens", bg=BG, fg=ACCENT, font=("Segoe UI", 20, "bold")).pack(
            anchor="w", padx=18, pady=(16, 0))
        tk.Label(self.root, text="Find the alarms that are overloading your operators.", bg=BG, fg=MUTED,
                 font=f).pack(anchor="w", padx=18)

        drop_text = ("Drop an alarm-log CSV here\nor click to choose a file" if TkinterDnD
                     else "Click to choose an alarm-log CSV")
        self.drop = tk.Label(self.root, text=drop_text, bg=PANEL, fg=FG, font=("Segoe UI", 12),
                             height=4, relief="flat", cursor="hand2", highlightthickness=2,
                             highlightbackground=LINE)
        self.drop.pack(fill="x", padx=18, pady=14)
        self.drop.bind("<Button-1>", lambda e: self._choose())
        if TkinterDnD:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self._on_drop)

        opts = tk.Frame(self.root, bg=BG)
        opts.pack(fill="x", padx=18)
        tk.Label(opts, text="Flood threshold (alarms / 10 min):", bg=BG, fg=MUTED, font=f).pack(side="left")
        self.flood = tk.Spinbox(opts, from_=2, to=100, width=4, font=f, bg=PANEL, fg=FG,
                                buttonbackground=PANEL, insertbackground=FG, relief="flat")
        self.flood.delete(0, "end")
        self.flood.insert(0, "10")
        self.flood.pack(side="left", padx=(6, 18))
        self.use_ai = tk.BooleanVar(value=False)
        tk.Checkbutton(opts, text="AI summary (needs Ollama)", variable=self.use_ai, bg=BG, fg=FG,
                       selectcolor=PANEL, activebackground=BG, activeforeground=FG, font=f).pack(side="left")

        btns = tk.Frame(self.root, bg=BG)
        btns.pack(fill="x", padx=18, pady=12)
        self.go = self._button(btns, "Analyze", self._analyze, primary=True)
        self.go.pack(side="left")
        self._button(btns, "Try sample data", self._sample).pack(side="left", padx=8)
        self.open_btn = self._button(btns, "Open full report", self._open)
        self.open_btn.pack(side="left")
        self.open_btn.configure(state="disabled")

        self.status = tk.Label(self.root, text="Choose a file to start.", bg=BG, fg=MUTED, font=f, anchor="w")
        self.status.pack(fill="x", padx=18)

        self.out = tk.Text(self.root, bg=PANEL, fg=FG, relief="flat", font=("Consolas", 10), wrap="word",
                           padx=12, pady=10, state="disabled", highlightthickness=0)
        self.out.pack(fill="both", expand=True, padx=18, pady=(8, 18))
        for k, c in STATUS_COLOR.items():
            self.out.tag_configure(k, foreground=c)
        self.out.tag_configure("h", foreground=ACCENT, font=("Consolas", 10, "bold"))
        self.out.tag_configure("m", foreground=MUTED)

    def _button(self, parent, text, cmd, primary=False):
        return tk.Button(parent, text=text, command=cmd, relief="flat", cursor="hand2",
                         bg=ACCENT if primary else "#1e2b40", fg=BG if primary else FG,
                         activebackground=ACCENT, activeforeground=BG, font=("Segoe UI", 10, "bold"),
                         padx=14, pady=6)

    # ---------- file selection ----------
    def _set_file(self, path):
        self.path = path
        self.drop.configure(text=os.path.basename(path), fg=ACCENT)
        self.status.configure(text="Ready. Click Analyze.", fg=MUTED)

    def _choose(self):
        p = filedialog.askopenfilename(title="Choose alarm-log CSV",
                                       filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if p:
            self._set_file(p)

    def _on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        if files:
            self._set_file(files[0])

    def _sample(self):
        self._set_file(SAMPLE)
        self._analyze(sample=True)

    # ---------- analysis (runs in a worker thread) ----------
    def _analyze(self, sample=False):
        if not self.path:
            self.status.configure(text="Choose a CSV file first.", fg=STATUS_COLOR["warn"])
            return
        try:
            flood = int(self.flood.get())
        except ValueError:
            flood = 10
        self.go.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.status.configure(text="Analyzing…", fg=ACCENT)
        args = (self.path, flood, self.use_ai.get(), sample or self.path == SAMPLE)
        threading.Thread(target=self._work, args=args, daemon=True).start()

    def _work(self, path, flood, use_ai, sample):
        try:
            a = analyze(load_alarm_log(path), flood_threshold=flood)
            recs = rule_recommendations(a)
            ai_text, note = (ai_summary(a) if use_ai else (None, "AI summary not requested."))
            out = os.path.splitext(path)[0] + "_report.html"
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(render(a, recs, ai_text, note, os.path.basename(path), sample))
            self.q.put(("done", (a, recs, out)))
        except Exception as e:  # show any problem in the window rather than crashing
            self.q.put(("error", str(e)))

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                self.go.configure(state="normal")
                if kind == "error":
                    self.status.configure(text="Couldn't analyze that file.", fg=STATUS_COLOR["bad"])
                    self._show([(payload, "bad")])
                else:
                    self._show_result(*payload)
        except queue.Empty:
            pass
        self.root.after(60, self._poll)

    def _show(self, parts):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        for text, tag in parts:
            self.out.insert("end", text, tag)
        self.out.configure(state="disabled")

    def _show_result(self, a, recs, out):
        self.report_path = out
        self.open_btn.configure(state="normal")
        self.status.configure(text=f"Done. {a.total_activations:,} activations, "
                                   f"{a.start:%d %b} to {a.end:%d %b %Y}. Report saved next to the CSV.",
                              fg=STATUS_COLOR["ok"])
        parts = [("ALARM KPIs\n", "h")]
        for k in a.kpis:
            parts += [(f"  {STATUS_TEXT[k.status]:<7}", k.status), (f"{k.name:<24}{k.display:>9}\n", None)]
        r = a.response
        if r.get("has_acks") and r["median_s"] is not None:
            parts += [("\nOPERATOR RESPONSE\n", "h"),
                      (f"  Median time to acknowledge  {r['median_s'] / 60:.1f} min\n"
                       f"  Never acknowledged          {r['unacked_pct']:.1f}%\n", None)]
        parts.append(("\nTOP ACTIONS\n", "h"))
        for i, rec in enumerate(recs[:4], 1):
            parts.append((f"  {i}. {rec}\n", None))
        parts.append(("\nOpen the full report for charts and tables.", "m"))
        self._show(parts)

    def _open(self):
        if self.report_path:
            webbrowser.open("file://" + os.path.abspath(self.report_path))


def main():
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    AlarmLensApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
