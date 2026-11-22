"""HUD look for Tkinter apps: animated core orb, trace line, glowing buttons, fade-in.

Pure Tkinter (no extra installs). Animations use root.after timers, so they never block.
"""
import math
import tkinter as tk
import tkinter.font as tkfont

# palette shared by the apps: emerald and champagne gold on deep forest black
BG = "#04110c"
PANEL = "#0a1f17"
PANEL2 = "#0f2a20"
LINE = "#1d3a2d"
CYAN = "#3ddc97"     # primary accent (emerald); name kept so existing code keeps working
VIOLET = "#d4b26a"   # secondary accent (champagne gold)
GOLD = VIOLET
EMERALD = CYAN
TEXT = "#eef4ef"
MUTED = "#9db3a6"
OK = "#3ddc97"
WARN = "#f0a64a"
ERR = "#ff6b6b"


def pick_font(root, *families, fallback="Segoe UI"):
    """First installed font family from the list (Bahnschrift ships with Windows 10+)."""
    have = {f.lower() for f in tkfont.families(root)}
    for f in families:
        if f.lower() in have:
            return f
    return fallback


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def blend(a, b, t):
    """Mix two #rrggbb colours; t=0 gives a, t=1 gives b."""
    (r1, g1, b1), (r2, g2, b2) = _hex(a), _hex(b)
    return "#%02x%02x%02x" % (round(r1 + (r2 - r1) * t), round(g1 + (g2 - g1) * t), round(b1 + (b2 - b1) * t))


def fade_in(root, ms=320):
    """Fade the window in (silently skipped where the platform has no alpha)."""
    try:
        root.attributes("-alpha", 0.0)
    except tk.TclError:
        return
    steps = 12

    def step(i=1):
        try:
            root.attributes("-alpha", min(1.0, i / steps))
        except tk.TclError:
            return
        if i < steps:
            root.after(ms // steps, step, i + 1)
    root.after(30, step)


class Core(tk.Canvas):
    """Animated orb. States: idle (slow breathing), think (spinning arcs), listen (pulsing red), offline (dim)."""

    COLORS = {"idle": CYAN, "think": VIOLET, "listen": ERR, "offline": "#4f6b5c", "ok": OK}

    def __init__(self, parent, size=44, bg=BG):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        self.size, self.state, self.t = size, "idle", 0.0
        self.bg = bg
        self._tick()

    def set_state(self, state):
        self.state = state if state in self.COLORS else "idle"

    def _tick(self):
        self.delete("all")
        s, c = self.size, self.size / 2
        col = self.COLORS[self.state]
        self.t += 0.06
        if self.state == "think":
            for k, ext in ((0, 110), (1, 70)):
                r = s * (0.44 - 0.11 * k)
                start = (self.t * (220 if k == 0 else -300)) % 360
                self.create_arc(c - r, c - r, c + r, c + r, start=start, extent=ext, style="arc",
                                outline=col if k == 0 else CYAN, width=2)
            core = s * 0.13
        else:
            speed = 2.2 if self.state == "listen" else 1.0
            pulse = 0.5 + 0.5 * math.sin(self.t * speed)
            for k in range(3):  # soft glow rings
                r = s * (0.26 + 0.07 * k + 0.03 * pulse)
                self.create_oval(c - r, c - r, c + r, c + r, outline=blend(self.bg, col, 0.55 - 0.17 * k), width=1)
            core = s * (0.15 + 0.03 * pulse)
        self.create_oval(c - core, c - core, c + core, c + core, fill=col, outline="")
        self.after(33, self._tick)


class Trace(tk.Canvas):
    """Thin line with a glowing segment travelling along it."""

    def __init__(self, parent, height=2, bg=BG):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.pos, self.bg = 0.0, bg
        self._tick()

    def _tick(self):
        self.delete("all")
        w = max(self.winfo_width(), 1)
        h = int(self["height"])
        self.create_rectangle(0, 0, w, h, fill=LINE, outline="")
        seg = w * 0.22
        x0 = (self.pos % 1.3 - 0.15) * w
        n = 24
        for i in range(n):  # gradient segment: transparent -> cyan -> violet -> transparent
            t = i / (n - 1)
            col = blend(CYAN, VIOLET, t)
            a = math.sin(math.pi * t)
            self.create_rectangle(x0 + seg * i / n, 0, x0 + seg * (i + 1) / n, h, fill=blend(LINE, col, a), outline="")
        self.pos += 0.006
        self.after(30, self._tick)


class GlowButton(tk.Label):
    """Flat button whose background eases between colours on hover and press."""

    def __init__(self, parent, text, command, font, primary=False, bg_parent=BG, padx=14, pady=7):
        self.base = CYAN if primary else PANEL2
        self.hover = "#8ff0c2" if primary else blend(PANEL2, CYAN, 0.22)
        fg = BG if primary else TEXT
        super().__init__(parent, text=text, bg=self.base, fg=fg, font=font, padx=padx, pady=pady, cursor="hand2")
        self.command, self.enabled, self._t, self._job = command, True, 0.0, None
        self.bind("<Enter>", lambda e: self._animate(1.0))
        self.bind("<Leave>", lambda e: self._animate(0.0))
        self.bind("<ButtonRelease-1>", self._click)

    def _click(self, _e):
        if self.enabled and self.command:
            self.configure(bg=CYAN if self.base != CYAN else "#c9f7df")
            self.after(90, lambda: self.configure(bg=blend(self.base, self.hover, self._t)))
            self.command()

    def _animate(self, target):
        if self._job:
            self.after_cancel(self._job)

        def step():
            self._t += (target - self._t) * 0.35
            if abs(target - self._t) < 0.02:
                self._t = target
            self.configure(bg=blend(self.base, self.hover, self._t))
            self._job = self.after(16, step) if self._t != target else None
        step()

    def set_enabled(self, on):
        self.enabled = on
        self.configure(fg=(BG if self.base == CYAN else TEXT) if on else MUTED, cursor="hand2" if on else "arrow")

    def set_colors(self, base, hover=None):
        self.base, self.hover = base, hover or blend(base, "#ffffff", 0.2)
        self.configure(bg=blend(self.base, self.hover, self._t))


class Dots:
    """Animated '· · ·' typing indicator at the end of a Text widget."""

    def __init__(self, text_widget, tag="dots"):
        self.w, self.tag, self.job, self.i = text_widget, tag, None, 0
        self.w.tag_configure(tag, foreground=VIOLET)

    def start(self):
        self.stop()
        self.w.configure(state="normal")
        self.w.mark_set("dots_start", "end-1c")
        self.w.mark_gravity("dots_start", "left")
        self.w.insert("end", "●○○", self.tag)
        self.w.configure(state="disabled")
        self._tick()

    def _tick(self):
        frames = ("●○○", "○●○", "○○●", "○●○")
        self.i = (self.i + 1) % len(frames)
        self.w.configure(state="normal")
        self.w.delete("dots_start", "end-1c")
        self.w.insert("end", frames[self.i], self.tag)
        self.w.configure(state="disabled")
        self.w.see("end")
        self.job = self.w.after(180, self._tick)

    def stop(self):
        if self.job:
            self.w.after_cancel(self.job)
            self.job = None
            self.w.configure(state="normal")
            self.w.delete("dots_start", "end-1c")
            self.w.configure(state="disabled")
