"""UI building blocks: background jobs, images, animation, buttons, banners and the game view."""

import queue
import threading
import time
import tkinter as tk
from collections import OrderedDict
from tkinter import ttk

from theme import ICONS, blend

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageTk
    HAS_PIL = True
except ImportError:  # running from source without Pillow: placeholders instead of images
    HAS_PIL = False

TRANSITION = 0.18  # seconds; every hover/focus/page transition uses this


# ---------------------------------------------------------------- background jobs

class Jobs:
    """Run functions on daemon worker threads and deliver results on the Tk thread.

    Newest jobs run first, so images for what is on screen now load before ones the user
    already scrolled past.
    """

    def __init__(self, root, workers=6):
        self.root = root
        self.todo = queue.LifoQueue()
        self.done = queue.Queue()
        for _ in range(workers):
            threading.Thread(target=self._work, daemon=True).start()
        self._poll()

    def submit(self, fn, callback):
        self.todo.put((fn, callback))

    def _work(self):
        while True:
            fn, callback = self.todo.get()
            try:
                result, error = fn(), None
            except Exception as e:
                result, error = None, e
            self.done.put((callback, result, error))

    def _poll(self):
        try:
            while True:
                callback, result, error = self.done.get_nowait()
                try:
                    callback(result, error)
                except tk.TclError:
                    pass  # the page that asked for it was closed meanwhile
        except queue.Empty:
            pass
        self.root.after(40, self._poll)


# ---------------------------------------------------------------- animation

def approach(current, target, dt):
    step = dt / TRANSITION
    return min(target, current + step) if target > current else max(target, current - step)


def ease(t):
    return t * t * (3 - 2 * t)


class Animator:
    """One shared ~60 fps ticker; objects implement step(dt) -> still_running."""

    def __init__(self, root):
        self.root = root
        self.active = set()
        self.job = None
        self.last = 0.0

    def start(self, obj):
        self.active.add(obj)
        if self.job is None:
            self.last = time.perf_counter()
            self.job = self.root.after(16, self._tick)

    def _tick(self):
        now = time.perf_counter()
        dt, self.last = min(now - self.last, 0.05), now
        for obj in list(self.active):
            try:
                running = obj.step(dt)
            except tk.TclError:
                running = False
            if not running:
                self.active.discard(obj)
        self.job = self.root.after(16, self._tick) if self.active else None


# ---------------------------------------------------------------- images

def fit_image(img, size, mode, radius=0):
    """Resize to `size`. 'cover' crops to fill when the shape is close, else letterboxes.
    `radius` rounds the corners (transparent outside)."""
    w, h = size
    img = img.convert("RGBA")
    src_ratio, dst_ratio = img.width / img.height, w / h
    if mode == "cover" and abs(src_ratio - dst_ratio) / dst_ratio < 0.25:
        scale = max(w / img.width, h / img.height)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                         Image.LANCZOS)
        left, top = (img.width - w) // 2, (img.height - h) // 2
        out = img.crop((left, top, left + w, top + h))
    else:
        scale = min(w / img.width, h / img.height)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                         Image.LANCZOS)
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    if radius:
        mask = Image.new("L", (w * 2, h * 2), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * 2 - 1, h * 2 - 1), radius * 2, fill=255)
        mask = mask.resize((w, h), Image.LANCZOS)
        alpha = out.getchannel("A")
        out.putalpha(Image.composite(alpha, Image.new("L", (w, h), 0), mask))
    return out


class ImageLoader:
    """Downloads (via core), resizes and caches images as Tk PhotoImages."""

    def __init__(self, jobs, limit=600):
        self.jobs = jobs
        self.cache = OrderedDict()
        self.limit = limit
        self.waiting = {}   # key -> callbacks to run when the image arrives
        self.missing = set()
        self.made = {}      # generated images (gradients, shadows)

    def get(self, key, fetch, size, mode="cover", on_ready=None, radius=0):
        """Return the PhotoImage now if it's ready; otherwise start loading it and return None."""
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        if not HAS_PIL or key in self.missing:
            return None
        if key in self.waiting:
            if on_ready:
                self.waiting[key].append(on_ready)
            return None
        self.waiting[key] = [on_ready] if on_ready else []

        def load():
            path = fetch()
            if path is None:
                return None
            with Image.open(path) as img:
                return fit_image(img, size, mode, radius)

        self.jobs.submit(load, lambda img, err: self._done(key, img, err))
        return None

    def _done(self, key, img, err):
        callbacks = self.waiting.pop(key, [])
        if err or img is None:
            self.missing.add(key)
            return
        self.cache[key] = ImageTk.PhotoImage(img)
        while len(self.cache) > self.limit:
            self.cache.popitem(last=False)
        for cb in callbacks:
            cb()

    def gradient(self, size, color, strength):
        """Bottom-to-top overlay: top half untouched, bottom half fades to `color` until
        fully covered. `strength` (0..1, 6 steps) drives the fade-in animation."""
        if not HAS_PIL:
            return None
        step = round(strength * 5)
        key = ("grad", size, color, step)
        if key not in self.made:
            w, h = size
            start, solid = 0.42, 0.70  # fade from 42% to 70% of the height, then solid
            rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
            column = Image.new("L", (1, h))
            for y in range(h):
                f = (y / h - start) / (solid - start)
                column.putpixel((0, y), round(255 * max(0.0, min(1.0, f)) * step / 5))
            layer = Image.new("RGBA", (w, h), rgb + (0,))
            layer.putalpha(column.resize((w, h)))
            self.made[key] = ImageTk.PhotoImage(layer)
        return self.made[key]

    def shadow(self, size, radius, dark):
        """A soft drop shadow for a rounded rectangle of `size`."""
        if not HAS_PIL:
            return None, 0
        key = ("shadow", size, radius, dark)
        blur = max(4, size[0] // 18)
        if key not in self.made:
            w, h = size
            img = Image.new("RGBA", (w + blur * 4, h + blur * 4), (0, 0, 0, 0))
            ImageDraw.Draw(img).rounded_rectangle(
                (blur * 2, blur * 2 + blur // 2, blur * 2 + w, blur * 2 + h + blur // 2), radius,
                fill=(0, 0, 0, 120 if dark else 46))
            self.made[key] = ImageTk.PhotoImage(img.filter(ImageFilter.GaussianBlur(blur)))
        return self.made[key], blur * 2


# ---------------------------------------------------------------- drawing helpers

def round_rect(canvas, x0, y0, x1, y1, r, **kw):
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, **kw)


def initials(name):
    words = [w for w in name.replace(":", " ").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def fit_text(font, text, max_w, cache=None):
    key = (text, str(font), int(max_w))
    if cache is not None and key in cache:
        return cache[key]
    result = text
    if font.measure(text) > max_w:
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.measure(text[:mid].rstrip() + "…") <= max_w:
                lo = mid
            else:
                hi = mid - 1
        result = text[:lo].rstrip() + "…"
    if cache is not None:
        if len(cache) > 6000:
            cache.clear()
        cache[key] = result
    return result


def wrap2(font, text, max_w, cache=None):
    """Up to two lines; the second is shortened with … if needed."""
    words, line = text.split(), ""
    for i, w in enumerate(words):
        test = f"{line} {w}".strip()
        if font.measure(test) <= max_w or not line:
            line = test
        else:
            rest = " ".join(words[i:])
            return [fit_text(font, line, max_w, cache), fit_text(font, rest, max_w, cache)]
    return [fit_text(font, line, max_w, cache)]


# ---------------------------------------------------------------- button

class CButton(tk.Canvas):
    """Rounded button: optional icon, text and trailing icon; smooth hover, visible focus
    ring, Enter/Space to press. Variants: primary, secondary, ghost, segment, chip."""

    def __init__(self, parent, app, text="", icon=None, icon_right=None, command=None,
                 variant="secondary", bg="bg", selected=False, compact=False, label=None):
        super().__init__(parent, highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self.app = app
        self.text, self.icon, self.icon_right = text, icon, icon_right
        self.command, self.variant, self.bgkey = command, variant, bg
        self.selected, self.compact = selected, compact
        self.label = label or text  # spoken/fallback name for icon-only buttons
        self.enabled = True
        self.t = 0.0
        self.target = 0.0
        self.focused = False
        self.pressed = False
        self.size = (0, 0)
        for seq, fn in (("<Enter>", self._enter), ("<Leave>", self._leave),
                        ("<ButtonPress-1>", self._press), ("<ButtonRelease-1>", self._release),
                        ("<FocusIn>", self._focus), ("<FocusOut>", self._unfocus),
                        ("<KeyPress-space>", lambda e: self.invoke()),
                        ("<Return>", lambda e: self.invoke())):
            self.bind(seq, fn)
        app.themed.add(self)
        self.redraw()

    def set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        if "enabled" in kw:
            self.configure(cursor="hand2" if self.enabled else "", takefocus=1 if self.enabled else 0)
        self.redraw()

    def invoke(self):
        if self.enabled and self.command:
            self.command()
        return "break"

    def step(self, dt):
        self.t = approach(self.t, self.target, dt)
        self.redraw()
        return self.t != self.target

    def _enter(self, e):
        if self.enabled:
            self.target = 1.0
            self.app.animator.start(self)

    def _leave(self, e):
        self.target, self.pressed = 0.0, False
        self.app.animator.start(self)

    def _press(self, e):
        if self.enabled:
            self.pressed = True
            self.redraw()

    def _release(self, e):
        was, self.pressed = self.pressed, False
        self.redraw()
        if was and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.invoke()

    def _focus(self, e):
        self.focused = True
        self.redraw()

    def _unfocus(self, e):
        self.focused = False
        self.redraw()

    def retheme(self):
        self.redraw()

    def _fonts(self):
        f = self.app.fonts
        return f["body_bold" if self.variant == "primary" else "body"], f["icon"]

    def _colors(self):
        p, t = self.app.palette, ease(self.t)
        base = p[self.bgkey]
        v = self.variant
        if not self.enabled:
            fill = p["raised"] if v in ("primary", "secondary") else base
            return fill, blend(p["muted"], fill, 0.35), fill
        if v == "primary":
            fill = blend(p["primary"], p["primary_hover"], t)
            fg, border = p["on_primary"], fill
        elif v == "secondary":
            fill = blend(p["surface"], p["raised"], t)
            fg, border = p["text"], p["border_strong"]
        elif v in ("segment", "chip") and self.selected:
            fill, fg, border = p["primary_soft"], p["primary_text"], p["primary"]
        elif v == "chip":
            fill = blend(p["surface"], p["raised"], t)
            fg, border = blend(p["muted"], p["text"], t), p["border_strong"]
        elif v == "segment":
            fill = blend(base, p["raised"], t)
            fg, border = blend(p["muted"], p["text"], t), fill
        else:  # ghost
            fill = blend(base, p["raised"], t)
            fg, border = p["text"], fill
        if self.pressed:
            fill = blend(fill, fg, 0.1)
        return fill, fg, border

    def redraw(self):
        S = self.app.scale
        p = self.app.palette
        tf, icf = self._fonts()
        ring = round(3 * S)
        h = max(round((30 if self.compact else 36) * S), tf.metrics("linespace") + round(12 * S))
        padx = round((10 if self.compact else 14) * S)
        gap = round(6 * S)
        parts = []
        if self.icon:
            parts.append(("icon", ICONS[self.icon]))
        if self.text:
            parts.append(("text", self.text))
        if self.icon_right:
            parts.append(("icon", ICONS[self.icon_right]))
        widths = [(icf if k == "icon" else tf).measure(v) for k, v in parts]
        content = sum(widths) + gap * max(0, len(parts) - 1)
        w = h if (self.icon and not self.text and not self.icon_right) else content + 2 * padx
        size = (w + 2 * ring, h + 2 * ring)
        if size != self.size:
            self.size = size
            self.configure(width=size[0], height=size[1])
        if self.cget("bg") != p[self.bgkey]:
            self.configure(bg=p[self.bgkey])
        self.delete("all")
        fill, fg, border = self._colors()
        r = round(8 * S)
        if self.focused:
            round_rect(self, 1, 1, size[0] - 1, size[1] - 1, r + ring, outline=p["focus"],
                       width=2, fill="")
        round_rect(self, ring, ring, ring + w, ring + h, r, fill=fill, outline=border)
        x = ring + (w - content) / 2
        for (kind, value), pw in zip(parts, widths):
            self.create_text(x, ring + h / 2 + (1 if kind == "icon" else 0), text=value,
                             anchor="w", fill=fg, font=icf if kind == "icon" else tf)
            x += pw + gap


# ---------------------------------------------------------------- banner

class Banner(tk.Frame):
    """An inline message (error / info / success) with optional actions and progress.
    Replaces pop-up message boxes."""

    def __init__(self, parent, app, pack_kw=None):
        super().__init__(parent, bd=0, highlightthickness=1)
        self.app = app
        self.kind = "info"
        self.pack_kw = pack_kw or {"fill": "x"}
        self.icon = tk.Label(self, bd=0, font=app.fonts["icon"])
        self.msg = tk.Label(self, bd=0, justify="left", anchor="w", font=app.fonts["body"])
        self.row2 = tk.Frame(self, bd=0)
        self.progress = ttk.Progressbar(self.row2, mode="indeterminate", length=round(160 * app.scale))
        self.close = CButton(self, app, icon="clear", variant="ghost", compact=True,
                             command=self.hide, label="Dismiss")
        S = app.scale
        self.icon.grid(row=0, column=0, padx=(round(14 * S), round(10 * S)), pady=round(12 * S), sticky="n")
        self.msg.grid(row=0, column=1, sticky="we", pady=round(12 * S))
        self.close.grid(row=0, column=2, padx=round(6 * S), pady=round(4 * S), sticky="n")
        self.columnconfigure(1, weight=1)
        self.buttons = []
        self.bind("<Configure>", lambda e: self.msg.configure(wraplength=max(120, e.width - round(110 * S))))
        app.themed.add(self)

    def show(self, kind, text, actions=(), progress=False, closable=True):
        self.kind = kind
        self.msg.configure(text=text)
        self.icon.configure(text=ICONS[{"error": "error", "success": "done"}.get(kind, "info")])
        for b in self.buttons:
            b.destroy()
        self.buttons = []
        bgkey = {"error": "error_soft", "success": "accent_soft"}.get(kind, "info_soft")
        for i, (label, cmd) in enumerate(actions):
            b = CButton(self.row2, self.app, text=label, command=cmd, compact=True, bg=bgkey,
                        variant="primary" if i == 0 else "secondary")
            b.pack(side="left", padx=(0, round(6 * self.app.scale)))
            self.buttons.append(b)
        if progress:
            self.progress.pack(side="left", pady=round(4 * self.app.scale))
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()
        if actions or progress:
            self.row2.grid(row=1, column=1, columnspan=2, sticky="w", pady=(0, round(12 * self.app.scale)))
        else:
            self.row2.grid_forget()
        if closable:
            self.close.grid()
        else:
            self.close.grid_remove()
        for b in self.buttons:
            b.set(bgkey=bgkey)
        self.close.set(bgkey=bgkey)
        self.retheme()
        if not self.winfo_ismapped():
            self.pack(**self.pack_kw)

    def hide(self):
        self.progress.stop()
        self.pack_forget()

    def retheme(self):
        p = self.app.palette
        bgkey = {"error": "error_soft", "success": "accent_soft"}.get(self.kind, "info_soft")
        fg = {"error": "error", "success": "accent"}.get(self.kind, "primary_text")
        bg = p[bgkey]
        border = {"error": p["error"], "success": p["accent"]}.get(self.kind, p["border_strong"])
        self.configure(bg=bg, highlightbackground=border, highlightcolor=border)
        self.icon.configure(bg=bg, fg=p[fg])
        self.msg.configure(bg=bg, fg=p["text"])
        self.row2.configure(bg=bg)


# ---------------------------------------------------------------- responsive toolbar

class FlowFrame(tk.Frame):
    """Lays children out left to right and wraps to a new row when the window is narrow.
    Children marked expand=True stretch to fill their row (down to `min_w`)."""

    def __init__(self, parent, app, bg="bg", gap=8):
        super().__init__(parent, bd=0, highlightthickness=0)
        self.app, self.bgkey = app, bg
        self.gap = round(gap * app.scale)
        self.items = []
        self.last_w = None
        self.bind("<Configure>", lambda e: self.relayout(e.width))
        app.themed.add(self)
        self.retheme()

    def add(self, widget, expand=False, min_w=0, max_w=None, break_after=False):
        self.items.append((widget, expand, round(min_w * self.app.scale),
                           round(max_w * self.app.scale) if max_w else None, break_after))

    def retheme(self):
        self.configure(bg=self.app.palette[self.bgkey])

    def relayout(self, width=None):
        width = width or self.winfo_width()
        if width <= 1:
            return
        self.last_w = width
        x = y = row_h = 0
        rows, row = [], []
        for item in self.items:
            w_, expand, min_w, max_w, brk = item
            if getattr(w_, "hidden", False):
                w_.place_forget()
                continue
            w = max(min_w, w_.winfo_reqwidth()) if expand else w_.winfo_reqwidth()
            if row and x + w > width:
                rows.append(row)
                row, x = [], 0
            row.append([item, x, w])
            x += w + self.gap
            if brk:
                rows.append(row)
                row, x = [], 0
        if row:
            rows.append(row)
        for row in rows:
            used = sum(r[2] for r in row) + self.gap * (len(row) - 1)
            spare = max(0, width - used)
            stretch = [r for r in row if r[0][1]]
            if stretch:
                extra = spare // len(stretch)
                shift = 0
                for r in row:
                    r[1] += shift
                    if r[0][1]:
                        grow = extra if r[0][3] is None else max(0, min(extra, r[0][3] - r[2]))
                        r[2] += grow
                        shift += grow
            row_h = max(r[0][0].winfo_reqheight() for r in row)
            for (w_, *_), rx, rw in row:
                w_.place(x=rx, y=y + (row_h - w_.winfo_reqheight()) // 2, width=rw)
            y += row_h + self.gap
        h = max(1, y - self.gap)
        if int(self.cget("height")) != h:
            self.configure(height=h)


# ---------------------------------------------------------------- scrollable page

class ScrollFrame(tk.Frame):
    """A vertically scrolling page; put widgets in `.inner`."""

    def __init__(self, parent, app, bg="bg"):
        super().__init__(parent, bd=0, highlightthickness=0)
        self.app, self.bgkey = app, bg
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._scrolled)
        self.inner = tk.Frame(self.canvas, bd=0)
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=(0, 0, e.width, e.height)))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind_all_wheel = lambda e: self.bind_all("<MouseWheel>", self._wheel)
        self.bind("<Enter>", self.bind_all_wheel)
        self.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))
        app.themed.add(self)
        self.retheme()

    def _scrolled(self, first, last):
        self.bar.set(first, last)

    def _wheel(self, event):
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-int(event.delta / 120) * 3, "units")

    def scroll_by(self, units):
        self.canvas.yview_scroll(units, "units")

    def position(self):
        return self.canvas.yview()[0]

    def restore(self, fraction):
        self.after(30, lambda: self.canvas.yview_moveto(fraction))

    def retheme(self):
        bg = self.app.palette[self.bgkey]
        self.configure(bg=bg)
        self.canvas.configure(bg=bg)
        self.inner.configure(bg=bg)


# ---------------------------------------------------------------- game view

class Item:
    __slots__ = ("kind", "x0", "y0", "x1", "y1", "game", "gid", "title", "count", "open", "parts")

    def __init__(self, kind, x0, y0, x1, y1, **kw):
        self.kind, self.x0, self.y0, self.x1, self.y1 = kind, x0, y0, x1, y1
        self.game = kw.get("game")
        self.gid = kw.get("gid")
        self.title = kw.get("title")
        self.count = kw.get("count")
        self.open = kw.get("open")
        self.parts = kw.get("parts", {})

    @property
    def key(self):
        return ("g", self.gid) if self.kind == "group" else ("a", self.game["appid"])

    def hit(self, x, y):
        for name, (a, b, c, d) in self.parts.items():
            if a <= x <= c and b <= y <= d:
                return name
        return "body"


class GameView(tk.Canvas):
    """The library as a grid of covers or a list of rows.

    Only what is on screen is drawn (smooth with thousands of games). Fully usable by
    keyboard: arrows move, Enter opens, Space marks as added, A opens Backloggd.
    """

    def __init__(self, parent, app):
        super().__init__(parent, highlightthickness=0, bd=0, takefocus=1)
        self.app = app
        self.S = app.scale
        self.mode = "grid"
        self.groups = []
        self.items = []
        self.total_h = 0
        self.hover = (None, None)
        self.focus_key = None
        self.has_focus = False
        self.anim = {}       # transition progress per (part, key)
        self.hot = set()     # keys whose transition heads to 1
        self.render_pending = False
        self.text_cache = {}
        self.last_region = None
        self.last_scroll = None
        self.scrollbar = None
        self.empty_btn = None
        self.metrics = {}
        self.configure(yscrollincrement=max(1, round(20 * self.S)))

        self.bind("<Configure>", lambda e: self.relayout())
        self.bind("<MouseWheel>", self.on_wheel)
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
        self.bind("<Button-3>", self.on_right_click)
        self.bind("<FocusIn>", self.on_focus_in)
        self.bind("<FocusOut>", self.on_focus_out)
        for key in ("Up", "Down", "Left", "Right", "Home", "End", "Prior", "Next"):
            self.bind(f"<{key}>", lambda e, k=key: self.move_focus(k))
        self.bind("<Return>", lambda e: self.activate("open"))
        self.bind("<KeyPress-space>", lambda e: self.activate("check"))
        self.bind("<KeyPress-a>", lambda e: self.activate("add"))
        app.themed.add(self)

    def retheme(self):
        self.text_cache.clear()
        self.relayout()

    # ---- data

    def set_data(self, groups, mode):
        self.groups = groups
        self.mode = mode
        self.relayout()

    def request_render(self):
        if not self.render_pending:
            self.render_pending = True
            self.after_idle(self.render)

    # ---- geometry (responsive: 375 / 768 / 1280 px and everything between)

    def tier(self, width):
        S = self.S
        return "wide" if width >= 768 * S else ("mid" if width >= 520 * S else "narrow")

    def list_columns(self, width):
        S = self.S
        tier = self.tier(width)
        pad = 4 * S
        c = {"tier": tier, "check": pad + 14 * S}
        c["thumb_w"], c["thumb_h"] = (96 * S, 45 * S) if tier != "narrow" else (64 * S, 30 * S)
        c["thumb"] = pad + 36 * S
        c["name"] = c["thumb"] + c["thumb_w"] + 14 * S
        right = width - pad - 4 * S
        c["last_x1"] = c["play_x1"] = None
        play_w = max(96 * S, self.app.fonts["body"].measure("9999h 59m") + 16 * S)
        last_w = max(96 * S, self.app.fonts["body"].measure("2026-12-31") + 16 * S)
        if tier == "wide":
            c["last_x1"] = right
            c["play_x1"] = right - last_w - 8 * S
            c["btn_x1"] = c["play_x1"] - play_w
        elif tier == "mid":
            c["play_x1"] = right
            c["btn_x1"] = right - play_w
        else:
            c["btn_x1"] = right
        f = self.app.fonts
        icon_w = f["icon"].measure(ICONS["open"])
        c["btn_w"] = max(36 * S, icon_w + 20 * S) if tier == "narrow" else             max(172 * S, f["body_bold"].measure("Open on Backloggd") + icon_w + 36 * S)
        c["btn_x0"] = c["btn_x1"] - c["btn_w"]
        c["name_x1"] = c["btn_x0"] - 16 * S
        return c

    def grid_metrics(self, width):
        S = self.S
        pad = round(4 * S)
        avail = width - 2 * pad
        cw, gap = round(150 * S), round(20 * S)
        cols = max(1, int((avail + gap) // (cw + gap)))
        if cols < 3:  # narrow window: two fluid columns
            cols, gap = 2, round(12 * S)
            cw = max(round(96 * S), int((avail - gap) / 2) // 8 * 8)
        else:  # spread leftover space into the gaps, within reason
            gap = min(round(36 * S), int((avail - cols * cw) / max(1, cols - 1)))
        ch = round(cw * 1.5)
        lh = self.app.fonts["body_bold"].metrics("linespace")
        name_h = 2 * lh + round(2 * S)
        btn_h = max(round(32 * S), self.app.fonts["body_bold"].metrics("linespace") + round(12 * S))
        card_h = ch + round(10 * S) + name_h + round(8 * S) + btn_h
        return {"pad": pad, "cols": cols, "cw": cw, "ch": ch, "gap": gap, "name_h": name_h,
                "btn_h": btn_h, "card_h": card_h, "row_gap": round(28 * S)}

    def relayout(self):
        S = self.S
        width = max(self.winfo_width(), 200)
        f = self.app.fonts
        group_h = max(round(52 * S), f["heading"].metrics("linespace") + round(24 * S))
        items = []
        y = round(4 * S)
        c = self.list_columns(width)
        g = self.grid_metrics(width)
        self.metrics = {"list": c, "grid": g}
        text_h = f["body_bold"].metrics("linespace") + f["small"].metrics("linespace")
        row_h = max(round((60 if c["tier"] == "narrow" else 64) * S), text_h + round(22 * S),
                    round(c["thumb_h"] + 16 * S))
        for gid, title, games, is_open in self.groups:
            items.append(Item("group", 0, y, width, y + group_h, gid=gid, title=title,
                              count=len(games), open=is_open))
            y += group_h + round(4 * S)
            if not is_open:
                continue
            if self.mode == "list":
                for game in games:
                    y0, y1 = y, y + row_h
                    mid = (y0 + y1) / 2
                    bh = max(16 * S, (f["body_bold"].metrics("linespace") + 12 * S) / 2)
                    parts = {
                        "check": (c["check"] - 13 * S, mid - 13 * S, c["check"] + 13 * S, mid + 13 * S),
                        "add": (c["btn_x0"], mid - bh, c["btn_x1"], mid + bh),
                    }
                    items.append(Item("row", 0, y0, width, y1, game=game, parts=parts))
                    y += row_h
            else:
                for i, game in enumerate(games):
                    col, row = i % g["cols"], i // g["cols"]
                    x0 = g["pad"] + col * (g["cw"] + g["gap"])
                    y0 = y + row * (g["card_h"] + g["row_gap"])
                    badge = 28 * S
                    by1 = y0 + g["card_h"]
                    parts = {
                        "check": (x0 + g["cw"] - badge - 8 * S, y0 + 8 * S, x0 + g["cw"] - 8 * S, y0 + 8 * S + badge),
                        "add": (x0, by1 - g["btn_h"], x0 + g["cw"], by1),
                        "cover": (x0, y0, x0 + g["cw"], y0 + g["ch"]),
                    }
                    items.append(Item("card", x0, y0, x0 + g["cw"], by1, game=game, parts=parts))
                if games:
                    rows = (len(games) + g["cols"] - 1) // g["cols"]
                    y += rows * (g["card_h"] + g["row_gap"])
            y += round(12 * S)
        self.items = items
        self.total_h = y + round(16 * S)
        region = (0, 0, round(width), round(max(self.total_h, self.winfo_height())))
        if region != self.last_region:
            self.last_region = region
            self.configure(scrollregion=region)
        self.request_render()

    def on_scroll(self, first, last):
        """yscrollcommand: move the scrollbar, and redraw only if the view really moved."""
        if self.scrollbar is not None:
            self.scrollbar.set(first, last)
        if (first, last) != self.last_scroll:
            self.last_scroll = (first, last)
            self.request_render()

    # ---- transitions

    def t(self, part, key):
        return ease(self.anim.get((part, key), 0.0))

    def set_hot(self, keys):
        keys = set(keys)
        if keys == self.hot:
            return
        for k in keys:
            self.anim.setdefault(k, 0.0)
        self.hot = keys
        self.app.animator.start(self)

    def step(self, dt):
        running = False
        for k in list(self.anim):
            target = 1.0 if k in self.hot else 0.0
            v = approach(self.anim[k], target, dt)
            if v == 0.0 and target == 0.0:
                del self.anim[k]
            else:
                self.anim[k] = v
            running |= v != target
        self.render()
        return running

    def refresh_hot(self):
        it, part = self.hover
        keys = []
        if it is not None:
            keys.append(("hover", it.key))
            if part in ("add", "check"):
                keys.append((part, it.key))
        if self.has_focus and self.focus_key is not None:
            keys.append(("hover", self.focus_key))
        self.set_hot(keys)

    # ---- drawing

    def render(self):
        self.render_pending = False
        self.delete("all")
        p = self.app.palette
        # Reconfiguring the canvas makes Tk re-announce the scroll position, which would
        # schedule another render: only touch it when the colour really changes
        if self.cget("bg") != p["bg"]:
            self.configure(bg=p["bg"])
        top = self.canvasy(0)
        bottom = top + self.winfo_height()
        self.empty_btn = None
        for it in self.items:
            if it.y1 < top - 20 or it.y0 > bottom + 20:
                continue
            if it.kind == "group":
                self.draw_group(it, p)
            elif it.kind == "row":
                self.draw_row(it, p)
            else:
                self.draw_card(it, p)
        if not self.items:
            self.draw_empty(p, top)

    def draw_focus(self, it, p, x0, y0, x1, y1, r):
        if self.has_focus and self.focus_key == it.key:
            round_rect(self, x0 - 4 * self.S, y0 - 4 * self.S, x1 + 4 * self.S, y1 + 4 * self.S,
                       r + 4 * self.S, outline=p["focus"], width=2, fill="")

    def draw_group(self, it, p):
        S, f = self.S, self.app.fonts
        h = self.t("hover", it.key)
        mid = (it.y0 + it.y1) / 2
        color = blend(p["text"], p["primary"], h)
        self.create_text(it.x0 + 8 * S, mid, text=ICONS["chev_down" if it.open else "chev_right"],
                         anchor="w", fill=color, font=f["icon"])
        tx = it.x0 + 16 * S + f["icon"].measure(ICONS["chev_down"])
        self.create_text(tx, mid, text=it.title, anchor="w", fill=color, font=f["heading"])
        w = f["heading"].measure(it.title)
        self.create_text(tx + w + 10 * S, mid + 1 * S, text=f"{it.count}", anchor="w",
                         fill=p["muted"], font=f["small"])
        self.create_line(it.x0 + 4 * S, it.y1 - 1, it.x1 - 4 * S, it.y1 - 1, fill=p["border"])
        self.draw_focus(it, p, it.x0 + 4 * S, it.y0 + 6 * S, it.x1 - 4 * S, it.y1 - 6 * S, 6 * S)

    def draw_check(self, rect, checked, hover, p, on_image=False):
        x0, y0, x1, y1 = rect
        if checked:
            fill, outline, fg = p["accent"], p["accent"], p["surface"]
        else:
            fill = blend(p["surface"], p["raised"], hover)
            outline = blend(p["border_strong"], p["primary"], hover)
            fg = blend(fill, p["muted"], hover)
        self.create_oval(x0, y0, x1, y1, fill=fill, outline=outline, width=2)
        if checked or hover > 0.05:
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2 + 1, text=ICONS["check"], fill=fg,
                             font=self.app.fonts["icon"])

    def draw_add(self, rect, game, p, hover, icon_only=False):
        """The per-game "Add to Backloggd" button: it only opens Backloggd in the browser."""
        S, f = self.S, self.app.fonts
        added = self.app.is_added(game)
        x0, y0, x1, y1 = rect
        if added:
            fill = blend(p["surface"], p["raised"], hover)
            fg, outline = p["text"], p["border_strong"]
            label = "Open on Backloggd"
        else:
            fill = blend(p["primary"], p["primary_hover"], hover)
            fg, outline = p["on_primary"], fill
            label = "Add to Backloggd"
        round_rect(self, x0, y0, x1, y1, 8 * S, fill=fill, outline=outline)
        if icon_only:
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2 + 1, text=ICONS["open"], fill=fg, font=f["icon"])
            return
        avail = x1 - x0 - 16 * S
        icon_w = f["icon"].measure(ICONS["open"]) + 6 * S
        short = "Open" if added else "Add"
        for tf, text, with_icon in ((f["body_bold"], label, True), (f["small_bold"], label, True),
                                    (f["small_bold"], label, False), (f["body_bold"], short, True)):
            if tf.measure(text) + (icon_w if with_icon else 0) <= avail:
                break
        w = tf.measure(text) + (icon_w if with_icon else 0)
        x = (x0 + x1 - w) / 2
        mid = (y0 + y1) / 2
        if with_icon:
            self.create_text(x, mid + 1, text=ICONS["open"], anchor="w", fill=fg, font=f["icon"])
            x += icon_w
        self.create_text(x, mid, text=text, anchor="w", fill=fg, font=tf)

    def placeholder(self, x0, y0, x1, y1, name, p, big=True, r=0):
        round_rect(self, x0, y0, x1, y1, r, fill=p["placeholder"], outline="")
        self.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=initials(name), fill=p["muted"],
                         font=self.app.fonts["heading" if big else "small_bold"])

    def draw_row(self, it, p):
        S, f, app = self.S, self.app.fonts, self.app
        g = it.game
        c = self.metrics["list"]
        hover = self.t("hover", it.key)
        if hover > 0:
            round_rect(self, it.x0, it.y0 + 2 * S, it.x1, it.y1 - 2 * S, 8 * S,
                       fill=blend(p["bg"], p["raised"], hover), outline="")
        else:
            self.create_line(it.x0 + 8 * S, it.y1, it.x1 - 8 * S, it.y1, fill=p["border"])
        self.draw_focus(it, p, it.x0 + 4 * S, it.y0 + 4 * S, it.x1 - 4 * S, it.y1 - 4 * S, 8 * S)
        mid = (it.y0 + it.y1) / 2
        self.draw_check(it.parts["check"], app.is_added(g), self.t("check", it.key), p)

        tx0, ty0 = c["thumb"], mid - c["thumb_h"] / 2
        size = (round(c["thumb_w"]), round(c["thumb_h"]))
        img = app.images.get(("header", g["appid"], size),
                             lambda: app.core.steam_art(g["appid"], "header"),
                             size, "cover", self.request_render, radius=round(5 * S))
        if img:
            self.create_image(tx0, ty0, image=img, anchor="nw")
        else:
            self.placeholder(tx0, ty0, tx0 + c["thumb_w"], ty0 + c["thumb_h"], app.name_of(g), p, False, 5 * S)

        name_w = c["name_x1"] - c["name"]
        if c["tier"] == "wide":
            sub = app.link_label(g)
        elif c["tier"] == "mid":
            sub = f"Last played {app.fmt_relative(g)}" if g["playtime"] else "Not played yet"
        else:
            sub = f"{app.fmt_playtime(g['playtime'])} · {app.fmt_relative(g)}" if g["playtime"] else "Not played yet"
        gap = 2 * S
        self.create_text(c["name"], mid - gap / 2, anchor="sw", fill=p["text"], font=f["body_bold"],
                         text=fit_text(f["body_bold"], app.name_of(g), name_w, self.text_cache))
        self.create_text(c["name"], mid + gap / 2, anchor="nw", fill=p["muted"], font=f["small"],
                         text=fit_text(f["small"], sub, name_w, self.text_cache))
        self.draw_add(it.parts["add"], g, p, self.t("add", it.key), icon_only=c["tier"] == "narrow")
        played = g["playtime"] > 0
        if c["play_x1"]:
            self.create_text(c["play_x1"], mid, anchor="e", fill=p["text"] if played else p["muted"],
                             text=app.fmt_playtime(g["playtime"]), font=f["body"])
        if c["last_x1"]:
            self.create_text(c["last_x1"], mid, anchor="e", fill=p["text"] if played else p["muted"],
                             text=app.fmt_last(g), font=f["body"])

    def draw_card(self, it, p):
        S, f, app = self.S, self.app.fonts, self.app
        g = it.game
        m = self.metrics["grid"]
        hover = self.t("hover", it.key)
        cx0, cy0 = it.x0, it.y0
        size = (m["cw"], m["ch"])
        r = round(10 * S)
        lift = round(3 * S * hover)  # covers rise a little on hover
        cy0 -= lift
        self.draw_focus(it, p, cx0, cy0, cx0 + size[0], cy0 + size[1], r)
        shadow, off = app.images.shadow(size, r, app.is_dark)
        if shadow:
            self.create_image(cx0 - off, cy0 - off, image=shadow, anchor="nw")

        def fetch():
            core = app.core
            return core.steam_art(g["appid"], "cover") or core.steam_art(g["appid"], "header")

        img = app.images.get(("cover", g["appid"], size), fetch, size, "cover",
                             self.request_render, radius=r)
        if img:
            round_rect(self, cx0, cy0, cx0 + size[0], cy0 + size[1], r, fill=p["placeholder"], outline="")
            self.create_image(cx0, cy0, image=img, anchor="nw")
        else:
            self.placeholder(cx0, cy0, cx0 + size[0], cy0 + size[1], app.name_of(g), p, r=r)

        if hover > 0.01:
            self.draw_overlay(g, p, cx0, cy0, size, hover)
        badge = list(it.parts["check"])
        badge[1] -= lift
        badge[3] -= lift
        self.draw_check(badge, app.is_added(g), self.t("check", it.key), p, on_image=True)

        ny = it.y0 + size[1] + 10 * S
        lh = f["body_bold"].metrics("linespace")
        for i, line in enumerate(wrap2(f["body_bold"], app.name_of(g), size[0], self.text_cache)):
            self.create_text(cx0, ny + i * lh, text=line, anchor="nw", fill=p["text"], font=f["body_bold"])
        self.draw_add(it.parts["add"], g, p, self.t("add", it.key), icon_only=size[0] < 112 * S)

    def draw_overlay(self, g, p, x0, y0, size, t):
        """Bottom-to-top gradient over the cover with playtime info in the covered half."""
        S, f, app = self.S, self.app.fonts, self.app
        grad = app.images.gradient(size, p["surface"], t)
        w, h = size
        if grad:
            self.create_image(x0, y0, image=grad, anchor="nw")
        else:  # no Pillow: a plain panel instead of a gradient
            self.create_rectangle(x0, y0 + h * 0.62, x0 + w, y0 + h, fill=p["surface"], outline="")
        fg = blend(p["surface"], p["text"], t)
        muted = blend(p["surface"], p["muted"], t)
        pad = 10 * S
        maxw = w - 2 * pad
        y = y0 + h - pad
        ach = app.achievement_summary(g["appid"])
        if ach:
            done, total = ach
            pct = round(100 * done / total)
            bar_y = y - 4 * S
            self.create_rectangle(x0 + pad, bar_y, x0 + w - pad, y, fill=blend(p["surface"], p["raised"], t),
                                  outline="")
            if pct:
                self.create_rectangle(x0 + pad, bar_y, x0 + pad + maxw * pct / 100, y,
                                      fill=blend(p["surface"], p["accent"], t), outline="")
            y = bar_y - 4 * S
            self.create_text(x0 + pad, y, anchor="sw", fill=muted, font=f["icon"], text=ICONS["star"])
            self.create_text(x0 + pad + 18 * S, y, anchor="sw", fill=muted, font=f["small"],
                             text=fit_text(f["small"], f"{pct}% · {done}/{total}", maxw - 18 * S))
            y -= f["small"].metrics("linespace") + 2 * S
        if g["playtime"]:
            last = f"Last played {app.fmt_relative(g)}"
            self.create_text(x0 + pad, y, anchor="sw", fill=muted, font=f["small"],
                             text=fit_text(f["small"], last, maxw))
            y -= f["small"].metrics("linespace") + 1 * S
            self.create_text(x0 + pad, y, anchor="sw", fill=fg, font=f["heading"],
                             text=fit_text(f["heading"], app.fmt_playtime(g["playtime"]), maxw))
        else:
            self.create_text(x0 + pad, y, anchor="sw", fill=fg, font=f["body_bold"],
                             text=fit_text(f["body_bold"], "Not played yet", maxw))

    def draw_empty(self, p, top):
        """Empty, loading and no-results states."""
        S, f = self.S, self.app.fonts
        state = self.app.empty_state()
        cx = self.winfo_width() / 2
        y = top + max(60 * S, self.winfo_height() * 0.22)
        self.create_text(cx, y, text=ICONS[state["icon"]], fill=p["muted"], font=f["icon_big"])
        y += 52 * S
        self.create_text(cx, y, text=state["title"], fill=p["text"], font=f["heading"], justify="center")
        y += 30 * S
        tid = self.create_text(cx, y, text=state["text"], fill=p["muted"], font=f["body"],
                               justify="center", width=min(420 * S, self.winfo_width() - 40 * S), anchor="n")
        bbox = self.bbox(tid)
        y = (bbox[3] if bbox else y) + 20 * S
        if state.get("action"):
            label = state["action"][0]
            hover = self.t("hover", ("empty", 0))
            w = f["body_bold"].measure(label) + 36 * S
            rect = (cx - w / 2, y, cx + w / 2, y + 38 * S)
            fill = blend(p["primary"], p["primary_hover"], hover)
            round_rect(self, *rect, 8 * S, fill=fill, outline=fill)
            if self.has_focus:
                round_rect(self, rect[0] - 4 * S, rect[1] - 4 * S, rect[2] + 4 * S, rect[3] + 4 * S,
                           12 * S, outline=p["focus"], width=2, fill="")
            self.create_text(cx, y + 19 * S, text=label, fill=p["on_primary"], font=f["body_bold"])
            self.empty_btn = (rect, state["action"][1])

    # ---- interaction

    def item_at(self, event):
        x, y = self.canvasx(event.x), self.canvasy(event.y)
        for it in self.items:
            if it.x0 <= x <= it.x1 and it.y0 <= y <= it.y1:
                return it, it.hit(x, y)
        return None, None

    def on_wheel(self, event):
        if self.total_h > self.winfo_height():
            self.yview_scroll(-int(event.delta / 120) * 3, "units")
            self.after_idle(lambda: self.on_motion(event))

    def on_motion(self, event):
        if self.empty_btn:
            (a, b, c, d), _ = self.empty_btn
            x, y = self.canvasx(event.x), self.canvasy(event.y)
            inside = a <= x <= c and b <= y <= d
            self.configure(cursor="hand2" if inside else "")
            self.set_hot([("hover", ("empty", 0))] if inside else [])
            return
        it, part = self.item_at(event)
        if part == "cover":
            part = "body"
        if (it, part) != self.hover:
            self.hover = (it, part)
            self.configure(cursor="hand2" if it is not None else "")
            self.refresh_hot()

    def on_leave(self, event):
        self.hover = (None, None)
        self.configure(cursor="")
        self.refresh_hot()

    def on_click(self, event):
        if self.empty_btn:
            (a, b, c, d), action = self.empty_btn
            x, y = self.canvasx(event.x), self.canvasy(event.y)
            if a <= x <= c and b <= y <= d:
                action()
            return
        it, part = self.item_at(event)
        if it is None:
            return
        self.focus_key = it.key
        if it.kind == "group":
            self.app.toggle_group(it.gid)
        elif part == "check":
            self.app.toggle_added(it.game)
        elif part == "add":
            self.app.open_backloggd(it.game)
        else:
            self.app.open_details(it.game)

    def on_right_click(self, event):
        it, _ = self.item_at(event)
        if it is not None and it.kind != "group":
            self.app.show_menu(it.game, event.x_root, event.y_root)

    # ---- keyboard

    def on_focus_in(self, event):
        self.has_focus = True
        if self.focus_key is None or not any(i.key == self.focus_key for i in self.items):
            self.focus_key = self.items[0].key if self.items else None
        self.refresh_hot()
        self.request_render()

    def on_focus_out(self, event):
        self.has_focus = False
        self.refresh_hot()
        self.request_render()

    def focused_item(self):
        for it in self.items:
            if it.key == self.focus_key:
                return it
        return None

    def move_focus(self, key):
        if not self.items:
            return "break"
        cur = self.focused_item() or self.items[0]
        idx = self.items.index(cur)
        target = cur
        if key in ("Left", "Right"):
            j = idx + (1 if key == "Right" else -1)
            if 0 <= j < len(self.items):
                target = self.items[j]
        elif key in ("Up", "Down"):
            target = self.nearest_in_row(cur, down=key == "Down") or cur
        elif key in ("Prior", "Next"):
            # Jump about one screen, landing on the closest item in that row
            down = key == "Next"
            goal = cur.y0 + (1 if down else -1) * self.winfo_height() * 0.8
            probe = cur
            while True:
                nxt = self.nearest_in_row(probe, down)
                if nxt is None or (nxt.y0 > goal if down else nxt.y0 < goal):
                    break
                probe = nxt
            target = probe
        elif key == "Home":
            target = self.items[0]
        elif key == "End":
            target = self.items[-1]
        self.focus_key = target.key
        self.ensure_visible(target)
        self.refresh_hot()
        self.request_render()
        return "break"

    def nearest_in_row(self, cur, down):
        """The item in the next row above/below `cur`, closest to it horizontally."""
        cands = [i for i in self.items if (i.y0 >= cur.y1 - 1 if down else i.y1 <= cur.y0 + 1)]
        if not cands:
            return None
        row_y = min(i.y0 for i in cands) if down else max(i.y0 for i in cands)
        cx = (cur.x0 + cur.x1) / 2
        return min((i for i in cands if i.y0 == row_y), key=lambda i: abs((i.x0 + i.x1) / 2 - cx))

    def ensure_visible(self, it):
        top = self.canvasy(0)
        h = self.winfo_height()
        total = max(self.total_h, h)
        margin = 12 * self.S
        if it.y0 - margin < top:
            self.yview_moveto(max(0, (it.y0 - margin) / total))
        elif it.y1 + margin > top + h:
            self.yview_moveto((it.y1 + margin - h) / total)

    def activate(self, action):
        if self.empty_btn and action == "open":
            self.empty_btn[1]()
            return "break"
        it = self.focused_item()
        if it is None:
            return "break"
        if it.kind == "group":
            if action in ("open", "check"):
                self.app.toggle_group(it.gid)
        elif action == "open":
            self.app.open_details(it.game)
        elif action == "check":
            self.app.toggle_added(it.game)
        elif action == "add":
            self.app.open_backloggd(it.game)
        return "break"


class ListHeader(tk.Canvas):
    """Column titles above the list view; click one to sort by it."""

    def __init__(self, parent, app, view):
        super().__init__(parent, highlightthickness=0, bd=0, height=self.wanted_height(app))
        self.app, self.view = app, view
        self.zones = []
        self.hover = None
        self.bind("<Configure>", lambda e: self.render())
        self.bind("<Button-1>", self.on_click)
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", lambda e: self.on_motion(None))
        app.themed.add(self)

    @staticmethod
    def wanted_height(app):
        return max(round(34 * app.scale), app.fonts["small"].metrics("linespace") + round(16 * app.scale))

    def retheme(self):
        h = self.wanted_height(self.app)
        if int(self.cget("height")) != h:
            self.configure(height=h)
        self.render()

    def render(self):
        self.delete("all")
        p, S, f = self.app.palette, self.app.scale, self.app.fonts
        if self.cget("bg") != p["bg"]:
            self.configure(bg=p["bg"])
        c = self.view.list_columns(max(self.view.winfo_width(), 200))
        H = int(self.cget("height"))
        y = H / 2
        self.zones = []
        cols = [("name", "Game", c["name"], "w")]
        if c["play_x1"]:
            cols.append(("playtime", "Playtime", c["play_x1"], "e"))
        if c["last_x1"]:
            cols.append(("last", "Last played", c["last_x1"], "e"))
        self.create_text(c["check"], y + 1, text=ICONS["check"], fill=p["muted"], font=f["icon"])
        for key, title, x, anchor in cols:
            active = self.app.sort_key == key
            color = p["primary_text"] if active else (p["text"] if self.hover == key else p["muted"])
            font = f["small_bold"] if active else f["small"]
            tw = font.measure(title)
            arrow = ICONS[self.app.sort_icon(key)] if active else ""
            aw = f["icon"].measure(arrow) + 4 * S if arrow else 0
            x0 = x if anchor == "w" else x - tw - aw
            self.create_text(x0, y, text=title, anchor="w", fill=color, font=font)
            if arrow:
                self.create_text(x0 + tw + 4 * S, y + 1, text=arrow, anchor="w", fill=color, font=f["icon"])
            self.zones.append((key, x0 - 6 * S, x0 + tw + aw + 6 * S))
        self.create_line(0, H - 1, self.winfo_width(), H - 1, fill=p["border"])

    def zone_at(self, x):
        for key, a, b in self.zones:
            if a <= x <= b:
                return key
        return None

    def on_motion(self, event):
        key = self.zone_at(event.x) if event else None
        if key != self.hover:
            self.hover = key
            self.configure(cursor="hand2" if key else "")
            self.render()

    def on_click(self, event):
        key = self.zone_at(event.x)
        if key:
            self.app.set_sort(key)


class Swatch(tk.Canvas):
    """A round color choice: shows the color, a check when chosen, and a keyboard focus ring."""

    def __init__(self, parent, app, color_key, command, bg="bg"):
        size = round(40 * app.scale)
        super().__init__(parent, width=size, height=size, highlightthickness=0, bd=0,
                         takefocus=1, cursor="hand2")
        self.app, self.color_key, self.command, self.bgkey = app, color_key, command, bg
        self.size = size
        self.selected = False
        self.focused = False
        self.hover = False
        self.bind("<Button-1>", lambda e: command())
        self.bind("<KeyPress-space>", lambda e: command())
        self.bind("<Return>", lambda e: command())
        self.bind("<Enter>", lambda e: self._set("hover", True))
        self.bind("<Leave>", lambda e: self._set("hover", False))
        self.bind("<FocusIn>", lambda e: self._set("focused", True))
        self.bind("<FocusOut>", lambda e: self._set("focused", False))
        app.themed.add(self)
        self.redraw()

    def _set(self, name, value):
        setattr(self, name, value)
        self.redraw()

    def retheme(self):
        self.redraw()

    def redraw(self):
        from theme import palette
        p = self.app.palette
        mode = "dark" if self.app.is_dark else "light"
        color = palette(mode, self.color_key)
        self.configure(bg=p[self.bgkey])
        self.delete("all")
        n, S = self.size, self.app.scale
        if self.focused or self.selected or self.hover:
            ring = p["focus"] if self.focused else (color["primary"] if self.selected else p["border_strong"])
            self.create_oval(1, 1, n - 1, n - 1, outline=ring, width=2)
        inset = round(6 * S)
        self.create_oval(inset, inset, n - inset, n - inset, fill=color["primary"], outline="")
        if self.selected:
            self.create_text(n / 2, n / 2 + 1, text=ICONS["check"], fill=color["on_primary"],
                             font=self.app.fonts["icon"])
