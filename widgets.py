"""Custom widgets: background jobs, image loading, tooltip and the grid/list game view."""

import queue
import threading
import tkinter as tk
from collections import OrderedDict
from tkinter import ttk

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:  # running from source without Pillow: placeholders instead of images
    HAS_PIL = False


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
                    pass  # the window that asked for it was closed meanwhile
        except queue.Empty:
            pass
        self.root.after(40, self._poll)


def fit_image(img, size, mode):
    """Resize to `size`. 'cover' crops to fill when the shape is close, else letterboxes."""
    w, h = size
    img = img.convert("RGBA")
    src_ratio, dst_ratio = img.width / img.height, w / h
    if mode == "cover" and abs(src_ratio - dst_ratio) / dst_ratio < 0.25:
        scale = max(w / img.width, h / img.height)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                         Image.LANCZOS)
        left, top = (img.width - w) // 2, (img.height - h) // 2
        return img.crop((left, top, left + w, top + h))
    scale = min(w / img.width, h / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                     Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    return canvas


class ImageLoader:
    """Downloads (via core), resizes and caches images as Tk PhotoImages."""

    def __init__(self, jobs, limit=500):
        self.jobs = jobs
        self.cache = OrderedDict()
        self.limit = limit
        self.waiting = {}   # key -> callbacks to run when the image arrives
        self.missing = set()

    def get(self, key, fetch, size, mode="cover", on_ready=None):
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
                return fit_image(img, size, mode)

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


# ---------------------------------------------------------------- tooltip

class Tooltip:
    """A small semi-transparent box that follows the mouse."""

    def __init__(self, root):
        self.root = root
        self.win = None
        self.label = None

    def show(self, text, x, y, palette):
        if self.win is None:
            self.win = tk.Toplevel(self.root)
            self.win.overrideredirect(True)
            self.win.attributes("-topmost", True)
            try:
                self.win.attributes("-alpha", 0.88)
            except tk.TclError:
                pass
            self.label = tk.Label(self.win, justify="left", padx=10, pady=6, bd=0)
            self.label.pack()
        self.label.configure(text=text, bg=palette["tip_bg"], fg=palette["tip_text"])
        self.win.configure(bg=palette["tip_bg"])
        self.move(x, y)
        self.win.deiconify()

    def move(self, x, y):
        if self.win is not None:
            self.win.geometry(f"+{x + 16}+{y + 18}")

    def hide(self):
        if self.win is not None:
            self.win.withdraw()


# ---------------------------------------------------------------- scrollable frame

class ScrollFrame(ttk.Frame):
    """A vertically scrolling container; put widgets in `.inner`."""

    def __init__(self, parent, bg):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=bg)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.inner = ttk.Frame(self.canvas, style="Card.TFrame")
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self._wheel))
        self.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))

    def _wheel(self, event):
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-int(event.delta / 120) * 3, "units")


# ---------------------------------------------------------------- game view

def round_rect(canvas, x0, y0, x1, y1, r, **kw):
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, **kw)


def initials(name):
    words = [w for w in name.replace(":", " ").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


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

    def hit(self, x, y):
        for name, (a, b, c, d) in self.parts.items():
            if a <= x <= c and b <= y <= d:
                return name
        return "body"


class GameView(tk.Canvas):
    """Draws the game library as a grid of covers or a list of rows.

    Only what is on screen is drawn, so large libraries stay fast.
    """

    def __init__(self, parent, app):
        super().__init__(parent, highlightthickness=0, bd=0)
        self.app = app
        self.mode = "grid"
        self.groups = []          # [(gid, title, [games], open)]
        self.items = []
        self.total_h = 0
        self.hover = (None, None)  # (item, part)
        self.tip_after = None
        self.render_pending = False
        self.text_cache = {}
        self.last_region = None
        self.last_scroll = None
        self.scrollbar = None
        s = app.scale
        self.S = s
        self.configure(yscrollincrement=max(1, round(20 * s)))

        self.bind("<Configure>", lambda e: self.relayout())
        self.bind("<MouseWheel>", self.on_wheel)
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
        self.bind("<Button-3>", self.on_right_click)

    # ---- data

    def set_data(self, groups, mode):
        self.groups = groups
        self.mode = mode
        self.relayout()

    def request_render(self):
        if not self.render_pending:
            self.render_pending = True
            self.after_idle(self.render)

    # ---- geometry

    def list_columns(self, width):
        S = self.S
        pad = 12 * S
        c = {"pad": pad, "check": pad + 12 * S, "thumb": pad + 42 * S,
             "thumb_w": 107 * S, "thumb_h": 50 * S}
        c["name"] = c["thumb"] + c["thumb_w"] + 14 * S
        c["last_x1"] = width - pad - 14 * S
        c["last_x0"] = c["last_x1"] - 100 * S
        c["play_x1"] = c["last_x0"] - 12 * S
        c["play_x0"] = c["play_x1"] - 100 * S
        c["btn_w"] = 158 * S
        # The button sits right after the name column; the name gets the remaining space
        c["btn_x1"] = c["play_x0"] - 16 * S
        c["btn_x0"] = c["btn_x1"] - c["btn_w"]
        c["name_x1"] = c["btn_x0"] - 14 * S
        return c

    def card_size(self):
        S = self.S
        cover_w, cover_h = round(150 * S), round(225 * S)
        pad = 8 * S
        name_h = 2 * self.app.fonts["bold"].metrics("linespace") + 4 * S
        btn_h = 30 * S
        return {"cover_w": cover_w, "cover_h": cover_h, "pad": pad, "name_h": name_h, "btn_h": btn_h,
                "w": cover_w + 2 * pad, "h": pad + cover_h + pad + name_h + 6 * S + btn_h + pad,
                "gap": 14 * S}

    def relayout(self):
        S = self.S
        width = max(self.winfo_width(), 200)
        pad = 12 * S
        group_h = 44 * S
        row_h = 66 * S
        items = []
        y = pad
        cols = self.list_columns(width)
        card = self.card_size()
        for gid, title, games, is_open in self.groups:
            items.append(Item("group", pad, y, width - pad, y + group_h,
                              gid=gid, title=title, count=len(games), open=is_open))
            y += group_h
            if not is_open:
                continue
            if self.mode == "list":
                for g in games:
                    y0, y1 = y, y + row_h - 6 * S
                    mid = (y0 + y1) / 2
                    parts = {
                        "check": (cols["check"] - 12 * S, mid - 12 * S, cols["check"] + 12 * S, mid + 12 * S),
                        "add": (cols["btn_x0"], mid - 15 * S, cols["btn_x1"], mid + 15 * S),
                    }
                    items.append(Item("row", pad, y0, width - pad, y1, game=g, parts=parts))
                    y += row_h
            else:
                per_row = max(1, int((width - 2 * pad + card["gap"]) // (card["w"] + card["gap"])))
                for i, g in enumerate(games):
                    col, row = i % per_row, i // per_row
                    x0 = pad + col * (card["w"] + card["gap"])
                    y0 = y + row * (card["h"] + card["gap"])
                    cx1 = x0 + card["pad"] + card["cover_w"]
                    cy0 = y0 + card["pad"]
                    badge = 26 * S
                    by1 = y0 + card["h"] - card["pad"]
                    parts = {
                        "check": (cx1 - badge - 6 * S, cy0 + 6 * S, cx1 - 6 * S, cy0 + 6 * S + badge),
                        "add": (x0 + card["pad"], by1 - card["btn_h"], cx1, by1),
                    }
                    items.append(Item("card", x0, y0, x0 + card["w"], y0 + card["h"], game=g, parts=parts))
                if games:
                    rows = (len(games) + per_row - 1) // per_row
                    y += rows * (card["h"] + card["gap"])
            y += 8 * S
        self.items = items
        self.total_h = y + pad
        region = (0, 0, round(width), round(max(self.total_h, self.winfo_height())))
        if region != self.last_region:
            self.last_region = region
            self.configure(scrollregion=region)
        self.request_render()

    def on_scroll(self, first, last):
        """yscrollcommand: move the scrollbar, and redraw only if the view really moved."""
        self.scrollbar.set(first, last)
        if (first, last) != self.last_scroll:
            self.last_scroll = (first, last)
            self.request_render()

    # ---- drawing

    def fit_text(self, text, font_name, max_w):
        key = (text, font_name, int(max_w))
        if key in self.text_cache:
            return self.text_cache[key]
        font = self.app.fonts[font_name]
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
        if len(self.text_cache) > 5000:
            self.text_cache.clear()
        self.text_cache[key] = result
        return result

    def wrap2(self, text, font_name, max_w):
        """Up to two lines; the second is shortened with … if needed."""
        font = self.app.fonts[font_name]
        words, line = text.split(), ""
        for i, w in enumerate(words):
            test = f"{line} {w}".strip()
            if font.measure(test) <= max_w or not line:
                line = test
            else:
                rest = " ".join(words[i:])
                return [self.fit_text(line, font_name, max_w), self.fit_text(rest, font_name, max_w)]
        return [self.fit_text(line, font_name, max_w)]

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
        for it in self.items:
            if it.y1 < top - 10 or it.y0 > bottom + 10:
                continue
            if it.kind == "group":
                self.draw_group(it, p)
            elif it.kind == "row":
                self.draw_row(it, p)
            else:
                self.draw_card(it, p)
        if not self.items:
            self.create_text(self.winfo_width() / 2, top + self.winfo_height() * 0.4,
                             text=self.app.empty_text(), fill=p["muted"], justify="center",
                             font=self.app.fonts["base"])

    def is_hover(self, it, part=None):
        h_item, h_part = self.hover
        return h_item is it and (part is None or h_part == part)

    def draw_group(self, it, p):
        S = self.S
        arrow = "▾" if it.open else "▸"
        mid = (it.y0 + it.y1) / 2 + 2 * S
        color = p["accent"] if self.is_hover(it) else p["text"]
        self.create_text(it.x0 + 2 * S, mid, text=f"{arrow}  {it.title}", anchor="w",
                         fill=color, font=self.app.fonts["heading"])
        w = self.app.fonts["heading"].measure(f"{arrow}  {it.title}")
        self.create_text(it.x0 + w + 12 * S, mid, text=f"{it.count} games", anchor="w",
                         fill=p["muted"], font=self.app.fonts["base"])
        self.create_line(it.x0, it.y1 - 4 * S, it.x1, it.y1 - 4 * S, fill=p["border"])

    def draw_check(self, x0, y0, x1, y1, checked, hover, p, round_=False):
        if round_:
            fill = p["accent"] if checked else p["surface"]
            self.create_oval(x0, y0, x1, y1, fill=fill,
                             outline=p["accent"] if (hover or checked) else p["border"], width=2)
        else:
            round_rect(self, x0, y0, x1, y1, 5 * self.S,
                       fill=p["accent"] if checked else p["surface"],
                       outline=p["accent"] if (hover or checked) else p["border"], width=2)
        if checked:
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="✓", fill=p["accent_text"],
                             font=self.app.fonts["bold"])

    def draw_button(self, rect, game, p, hover):
        added = self.app.is_added(game)
        x0, y0, x1, y1 = rect
        if added:
            fill, fg, outline = p["surface2"], p["text"], p["accent"] if hover else p["border"]
            label = "Open on Backloggd ↗"
        else:
            fill = p["accent_hover"] if hover else p["accent"]
            fg, outline, label = p["accent_text"], fill, "Add to Backloggd ↗"
        round_rect(self, x0, y0, x1, y1, 7 * self.S, fill=fill, outline=outline)
        self.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=label, fill=fg,
                         font=self.app.fonts["bold"])

    def placeholder(self, x0, y0, x1, y1, name, p, big=True):
        self.create_rectangle(x0, y0, x1, y1, fill=p["placeholder"], outline="")
        self.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=initials(name), fill=p["muted"],
                         font=self.app.fonts["title" if big else "bold"])

    def draw_row(self, it, p):
        S = self.S
        g = it.game
        c = self.list_columns(max(self.winfo_width(), 200))
        hover = self.is_hover(it)
        round_rect(self, it.x0, it.y0, it.x1, it.y1, 8 * S, fill=p["surface"],
                   outline=p["accent"] if hover else p["border"])
        mid = (it.y0 + it.y1) / 2
        self.draw_check(*it.parts["check"], self.app.is_added(g), self.is_hover(it, "check"), p)

        tx0, ty0 = c["thumb"], mid - c["thumb_h"] / 2
        size = (round(c["thumb_w"]), round(c["thumb_h"]))
        img = self.app.images.get(("header", g["appid"], size),
                                  lambda: self.app.core.steam_art(g["appid"], "header"),
                                  size, "cover", self.request_render)
        if img:
            self.create_image(tx0, ty0, image=img, anchor="nw")
        else:
            self.placeholder(tx0, ty0, tx0 + c["thumb_w"], ty0 + c["thumb_h"], self.app.name_of(g), p, False)

        name_w = c["name_x1"] - c["name"]
        self.create_text(c["name"], mid - 9 * S, anchor="w", fill=p["text"], font=self.app.fonts["bold"],
                         text=self.fit_text(self.app.name_of(g), "bold", name_w))
        self.create_text(c["name"], mid + 11 * S, anchor="w", fill=p["muted"], font=self.app.fonts["small"],
                         text=self.fit_text(self.app.link_label(g), "small", name_w))
        self.draw_button(it.parts["add"], g, p, self.is_hover(it, "add"))
        self.create_text(c["play_x1"], mid, anchor="e", fill=p["text"] if g["playtime"] else p["muted"],
                         text=self.app.fmt_playtime(g["playtime"]), font=self.app.fonts["base"])
        self.create_text(c["last_x1"], mid, anchor="e", fill=p["text"] if g["playtime"] else p["muted"],
                         text=self.app.fmt_last(g), font=self.app.fonts["base"])

    def draw_card(self, it, p):
        S = self.S
        g = it.game
        card = self.card_size()
        hover = self.is_hover(it)
        round_rect(self, it.x0, it.y0, it.x1, it.y1, 10 * S, fill=p["surface"],
                   outline=p["accent"] if hover else p["border"], width=2 if hover else 1)
        cx0, cy0 = it.x0 + card["pad"], it.y0 + card["pad"]
        size = (card["cover_w"], card["cover_h"])

        def fetch():
            core = self.app.core
            return core.steam_art(g["appid"], "cover") or core.steam_art(g["appid"], "header")

        img = self.app.images.get(("cover", g["appid"], size), fetch, size, "cover", self.request_render)
        if img:
            self.create_rectangle(cx0, cy0, cx0 + size[0], cy0 + size[1], fill=p["placeholder"], outline="")
            self.create_image(cx0, cy0, image=img, anchor="nw")
        else:
            self.placeholder(cx0, cy0, cx0 + size[0], cy0 + size[1], self.app.name_of(g), p)
        self.draw_check(*it.parts["check"], self.app.is_added(g), self.is_hover(it, "check"), p, round_=True)

        ny = cy0 + size[1] + card["pad"]
        lh = self.app.fonts["bold"].metrics("linespace")
        for i, line in enumerate(self.wrap2(self.app.name_of(g), "bold", size[0])):
            self.create_text(cx0, ny + i * lh, text=line, anchor="nw", fill=p["text"],
                             font=self.app.fonts["bold"])
        self.draw_button(it.parts["add"], g, p, self.is_hover(it, "add"))

    # ---- interaction

    def item_at(self, event):
        x, y = self.canvasx(event.x), self.canvasy(event.y)
        for it in self.items:
            if it.x0 <= x <= it.x1 and it.y0 <= y <= it.y1:
                return it, it.hit(x, y)
        return None, None

    def on_wheel(self, event):
        self.hide_tip()
        if self.total_h > self.winfo_height():
            self.yview_scroll(-int(event.delta / 120) * 3, "units")
            self.on_motion(event)

    def on_motion(self, event):
        it, part = self.item_at(event)
        if (it, part) != self.hover:
            self.hover = (it, part)
            self.configure(cursor="hand2" if it is not None else "")
            self.request_render()
            self.hide_tip()
            if it is not None and it.kind != "group":
                self.tip_after = self.after(450, lambda: self.show_tip(it))
        elif self.app.tooltip.win is not None and it is not None:
            self.app.tooltip.move(event.x_root, event.y_root)

    def show_tip(self, it):
        self.tip_after = None
        if self.hover[0] is not it:
            return
        x, y = self.winfo_pointerxy()
        self.app.tooltip.show(self.app.tip_text(it.game), x, y, self.app.palette)

    def hide_tip(self):
        if self.tip_after:
            self.after_cancel(self.tip_after)
            self.tip_after = None
        self.app.tooltip.hide()

    def on_leave(self, event):
        self.hover = (None, None)
        self.hide_tip()
        self.configure(cursor="")
        self.request_render()

    def on_click(self, event):
        it, part = self.item_at(event)
        self.hide_tip()
        if it is None:
            return
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
        self.hide_tip()
        if it is not None and it.kind != "group":
            self.app.show_menu(it.game, event.x_root, event.y_root)


class ListHeader(tk.Canvas):
    """Column titles above the list view; click one to sort by it."""

    def __init__(self, parent, app, view):
        super().__init__(parent, highlightthickness=0, bd=0, height=round(28 * app.scale))
        self.app, self.view = app, view
        self.zones = []
        self.hover = None
        self.bind("<Configure>", lambda e: self.render())
        self.bind("<Button-1>", self.on_click)
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", lambda e: self.on_motion(None))

    def render(self):
        self.delete("all")
        p, S = self.app.palette, self.app.scale
        if self.cget("bg") != p["bg"]:
            self.configure(bg=p["bg"])
        c = self.view.list_columns(max(self.view.winfo_width(), 200))
        y = 14 * S
        self.zones = []
        f = self.app.fonts["bold"]
        cols = [("name", "Game", c["name"], "w"),
                ("playtime", "Playtime", c["play_x1"], "e"),
                ("last", "Last played", c["last_x1"], "e")]
        self.create_text(c["check"], y, text="Added", fill=p["muted"], font=self.app.fonts["small"])
        for key, title, x, anchor in cols:
            label = title + self.app.sort_arrow(key)
            active = self.app.sort_key == key
            color = p["accent"] if (active or self.hover == key) else p["muted"]
            self.create_text(x, y, text=label, anchor=anchor, fill=color, font=f)
            w = f.measure(label)
            x0 = x if anchor == "w" else x - w
            self.zones.append((key, x0 - 6 * S, x0 + w + 6 * S))

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
