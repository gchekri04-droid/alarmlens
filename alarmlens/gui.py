"""AlarmLens window: drop (or choose) an alarm-log CSV, click Analyze, open the report.

Run:  python -m alarmlens.gui
Drag-and-drop uses the optional 'tkinterdnd2' package; without it, use the Choose button.
"""
import math
import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog

from . import hud
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

BG, PANEL, LINE, FG, MUTED, ACCENT = hud.BG, hud.PANEL, hud.LINE, hud.TEXT, hud.MUTED, hud.CYAN
STATUS_COLOR = {"ok": hud.OK, "warn": hud.WARN, "bad": hud.ERR}
STATUS_TEXT = {"ok": "OK", "warn": "Watch", "bad": "Action"}


class AlarmLensApp:
    def __init__(self, root):
        self.root = root
        self.path = None
        self.report_path = None
        self.q = queue.Queue()
        self._reveal_job = None
        root.title("AlarmLens")
        root.geometry("760x700")
        root.minsize(580, 560)
        root.configure(bg=BG)
        hud.fade_in(root)
        self.f_disp = hud.pick_font(root, "Bahnschrift", "Segoe UI Semibold", "DejaVu Sans")
        self.f_body = hud.pick_font(root, "Segoe UI", "Inter", "DejaVu Sans")
        self.f_mono = hud.pick_font(root, "Cascadia Mono", "Consolas", "DejaVu Sans Mono")
        self.f_serif = hud.pick_font(root, "Constantia", "Georgia", "DejaVu Serif")
        self._build()
        root.after(60, self._poll)

    # ---------- layout ----------
    def _build(self):
        f = (self.f_body, 10)
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=20, pady=(16, 10))
        self.core = hud.Core(head, size=46)
        self.core.pack(side="left")
        t = tk.Frame(head, bg=BG)
        t.pack(side="left", padx=(10, 0))
        tk.Label(t, text=" ".join("ALARMLENS"), bg=BG, fg=FG, font=(self.f_serif, 21)).pack(anchor="w")
        tk.Label(t, text="FIND THE ALARMS OVERLOADING YOUR OPERATORS", bg=BG, fg=hud.GOLD,
                 font=(self.f_mono, 9)).pack(anchor="w")
        self.trace = hud.Trace(self.root, height=2)
        self.trace.pack(fill="x", padx=20)

        drop_text = ("⇣  Drop an alarm-log CSV here\nor click to choose a file" if TkinterDnD
                     else "Click to choose an alarm-log CSV")
        self.drop_border = tk.Frame(self.root, bg=LINE, padx=1, pady=1)
        self.drop_border.pack(fill="x", padx=20, pady=14)
        self.drop = tk.Label(self.drop_border, text=drop_text, bg=PANEL, fg=MUTED, font=(self.f_body, 12),
                             height=4, cursor="hand2")
        self.drop.pack(fill="x")
        self.drop.bind("<Button-1>", lambda e: self._choose())
        self.drop.bind("<Enter>", lambda e: self.drop_border.configure(bg=ACCENT))
        self.drop.bind("<Leave>", lambda e: self.drop_border.configure(bg=LINE))
        if TkinterDnD:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self._on_drop)
            self.drop.dnd_bind("<<DropEnter>>", lambda e: (self.drop_border.configure(bg=ACCENT), e.action)[1])
            self.drop.dnd_bind("<<DropLeave>>", lambda e: (self.drop_border.configure(bg=LINE), e.action)[1])

        opts = tk.Frame(self.root, bg=BG)
        opts.pack(fill="x", padx=20)
        tk.Label(opts, text="Flood threshold (alarms / 10 min)", bg=BG, fg=MUTED, font=f).pack(side="left")
        self.flood = tk.Spinbox(opts, from_=2, to=100, width=4, font=(self.f_mono, 10), bg=PANEL, fg=FG,
                                buttonbackground=PANEL, insertbackground=ACCENT, relief="flat",
                                highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT)
        self.flood.delete(0, "end")
        self.flood.insert(0, "10")
        self.flood.pack(side="left", padx=(8, 18))
        self.use_ai = tk.BooleanVar(value=False)
        tk.Checkbutton(opts, text="AI summary (needs Ollama)", variable=self.use_ai, bg=BG, fg=MUTED,
                       selectcolor=PANEL, activebackground=BG, activeforeground=FG, font=f,
                       highlightthickness=0, bd=0).pack(side="left")

        btns = tk.Frame(self.root, bg=BG)
        btns.pack(fill="x", padx=20, pady=14)
        self.go = hud.GlowButton(btns, "Analyze", self._analyze, font=(self.f_body, 10, "bold"), primary=True)
        self.go.pack(side="left")
        hud.GlowButton(btns, "Try sample data", self._sample, font=(self.f_body, 10)).pack(side="left", padx=8)
        self.open_btn = hud.GlowButton(btns, "Open full report  ↗", self._open, font=(self.f_body, 10))
        self.open_btn.pack(side="left")
        self.open_btn.set_enabled(False)

        self.status = tk.Label(self.root, text="CHOOSE A FILE TO START", bg=BG, fg=MUTED, font=(self.f_mono, 9), anchor="w")
        self.status.pack(fill="x", padx=20)
        self.bar = tk.Canvas(self.root, height=3, bg=BG, highlightthickness=0, bd=0)
        self.bar.pack(fill="x", padx=20, pady=(6, 0))
        self._bar_job, self._bar_x = None, 0.0

        box = tk.Frame(self.root, bg=LINE, padx=1, pady=1)
        box.pack(fill="both", expand=True, padx=20, pady=(8, 20))
        self.out = tk.Text(box, bg=PANEL, fg=FG, relief="flat", bd=0, font=(self.f_mono, 10), wrap="word",
                           padx=14, pady=12, state="disabled", highlightthickness=0, spacing1=2)
        self.out.pack(fill="both", expand=True)
        for k, c in STATUS_COLOR.items():
            self.out.tag_configure(k, foreground=c)
        self.out.tag_configure("h", foreground=hud.GOLD, font=(self.f_mono, 10, "bold"))
        self.out.tag_configure("m", foreground=MUTED)

    def _status(self, text, color=MUTED):
        self.status.configure(text=text.upper(), fg=color)

    # animated scanning bar while analyzing
    def _bar_start(self):
        self._bar_stop()

        def tick():
            w = max(self.bar.winfo_width(), 1)
            self.bar.delete("all")
            self.bar.create_rectangle(0, 0, w, 3, fill=LINE, outline="")
            x = (self._bar_x % 1.4 - 0.2) * w
            n = 20
            for i in range(n):
                t = i / (n - 1)
                col = hud.blend(LINE, hud.blend(hud.CYAN, hud.VIOLET, t), math.sin(math.pi * t))
                self.bar.create_rectangle(x + w * 0.3 * i / n, 0, x + w * 0.3 * (i + 1) / n, 3, fill=col, outline="")
            self._bar_x += 0.025
            self._bar_job = self.root.after(16, tick)
        tick()

    def _bar_stop(self):
        if self._bar_job:
            self.root.after_cancel(self._bar_job)
            self._bar_job = None
        self.bar.delete("all")

    # ---------- file selection ----------
    def _set_file(self, path):
        self.path = path
        self.drop.configure(text="◆  " + os.path.basename(path), fg=ACCENT)
        self._status("Ready. Click Analyze.")

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
            self._status("Choose a CSV file first.", STATUS_COLOR["warn"])
            return
        try:
            flood = int(self.flood.get())
        except ValueError:
            flood = 10
        self.go.set_enabled(False)
        self.open_btn.set_enabled(False)
        self._status("Analyzing…", ACCENT)
        self.core.set_state("think")
        self._bar_start()
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
                self.go.set_enabled(True)
                self._bar_stop()
                if kind == "error":
                    self.core.set_state("offline")
                    self._status("Couldn't analyze that file.", STATUS_COLOR["bad"])
                    self._show([(payload, "bad")])
                else:
                    self._show_result(*payload)
        except queue.Empty:
            pass
        self.root.after(60, self._poll)

    def _show(self, parts, animate=False):
        if self._reveal_job:
            self.root.after_cancel(self._reveal_job)
            self._reveal_job = None
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.configure(state="disabled")
        if not animate:
            self.out.configure(state="normal")
            for text, tag in parts:
                self.out.insert("end", text, tag)
            self.out.configure(state="disabled")
            return

        def step(i=0):
            if i >= len(parts):
                self._reveal_job = None
                return
            text, tag = parts[i]
            self.out.configure(state="normal")
            self.out.insert("end", text, tag)
            self.out.configure(state="disabled")
            self._reveal_job = self.root.after(22 if text.endswith("\n") else 0, step, i + 1)
        step()

    def _show_result(self, a, recs, out):
        self.report_path = out
        self.open_btn.set_enabled(True)
        self.core.set_state("ok")
        self._status(f"Done · {a.total_activations:,} activations · "
                     f"{a.start:%d %b} to {a.end:%d %b %Y} · report saved next to the CSV", STATUS_COLOR["ok"])
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
        self._show(parts, animate=True)

    def _open(self):
        if self.report_path:
            webbrowser.open("file://" + os.path.abspath(self.report_path))


def main():
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    AlarmLensApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
