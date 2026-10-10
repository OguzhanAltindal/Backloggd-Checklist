"""Backloggd Checklist: desktop app.

Run by double-clicking this file, or with:  pythonw app.pyw
"""

import sys
import tkinter as tk
import weakref
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import ttk

import checklist_core as core
import theme
from theme import ICONS
from widgets import (Animator, Banner, CButton, FlowFrame, GameView, ImageLoader, Jobs, ListHeader,
                     ScrollFrame, Swatch, approach, ease, fit_text, round_rect)

STEAM_KEY_URL = "https://steamcommunity.com/dev/apikey"
STEAM_PROFILE_URL = "https://steamcommunity.com/my/profile"
STEAM_PRIVACY_URL = "https://steamcommunity.com/my/edit/settings"
TWITCH_CREATE_URL = "https://dev.twitch.tv/console/apps/create"


def fmt_playtime(m):
    if not m:
        return "Not played"
    h, mm = divmod(m, 60)
    return f"{h}h {mm}m" if h else f"{mm}m"


def fmt_date(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "—"


def fmt_relative(ts):
    if not ts:
        return "never"
    days = (datetime.now() - datetime.fromtimestamp(ts)).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    for limit, size, unit in ((14, 1, "day"), (60, 7, "week"), (730, 30, "month")):
        if days < limit:
            n = days // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    n = days // 365
    return f"{n} years ago"


# ---------------------------------------------------------------- pages

class Page(tk.Frame):
    """A full view inside the main window. Pages replace every pop-up the app used to have."""

    persistent = False  # kept alive between visits (the library) or rebuilt each time

    def __init__(self, app, params):
        super().__init__(app.content, bd=0, highlightthickness=0)
        self.app, self.params = app, params
        self.S = app.scale
        self.wraps = []  # (label, max width, side margin) re-wrapped on resize
        self.bind("<Configure>", self._resized)
        app.themed.add(self)
        self.retheme()

    def crumbs(self):
        return ["Library"]

    def capture(self):
        return {}

    def restore(self, state):
        pass

    def on_show(self):
        pass

    def retheme(self):
        self.configure(bg=self.app.palette["bg"])

    def wrap(self, label, max_w=640, margin=64):
        self.wraps.append((label, max_w, margin))
        return label

    def _resized(self, event):
        for label, max_w, margin in self.wraps:
            if label.winfo_exists():
                label.configure(wraplength=max(160, min(max_w * self.S, event.width - margin * self.S)))
        self.resized(event.width)

    def resized(self, width):
        pass

    def side_pad(self, width=None):
        width = width or self.winfo_width()
        return round((16 if width < 600 * self.S else 32) * self.S)


class SearchBox(tk.Frame):
    """Search field with icon, placeholder and clear button."""

    def __init__(self, parent, app, var, hint):
        super().__init__(parent, bd=0, highlightthickness=1)
        self.app, self.var, self.hint_text = app, var, hint
        S = app.scale
        self.configure(height=round(36 * S), width=round(260 * S))
        self.pack_propagate(False)
        self.icon = tk.Label(self, text=ICONS["search"], font=app.fonts["icon"], bd=0)
        self.icon.pack(side="left", padx=(round(10 * S), round(6 * S)))
        self.clear = CButton(self, app, icon="clear", variant="ghost", compact=True, bg="surface",
                             command=lambda: (var.set(""), self.entry.focus_set()), label="Clear search")
        self.entry = tk.Entry(self, textvariable=var, bd=0, relief="flat", font=app.fonts["body"])
        self.entry.pack(side="left", fill="both", expand=True)
        self.hint = tk.Label(self, text=hint, font=app.fonts["body"], bd=0, anchor="w")
        self.hint.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", lambda e: self.update_state())
        self.entry.bind("<FocusOut>", lambda e: self.update_state())
        self.entry.bind("<Escape>", lambda e: var.set(""))
        var.trace_add("write", lambda *a: self.update_state())
        app.themed.add(self)
        self.retheme()
        self.update_state()

    def update_state(self):
        if self.var.get():
            self.hint.place_forget()
            if not self.clear.winfo_ismapped():
                self.clear.pack(side="right", padx=round(2 * self.app.scale))
        else:
            self.hint.place(in_=self.entry, x=0, rely=0.5, anchor="w")
            self.clear.pack_forget()
        focused = self.focus_get() is self.entry
        p = self.app.palette
        self.configure(highlightbackground=p["focus"] if focused else p["border_strong"],
                       highlightcolor=p["focus"])

    def retheme(self):
        p = self.app.palette
        # The field grows with the text size
        h = max(round(36 * self.app.scale), self.app.fonts["body"].metrics("linespace") + round(14 * self.app.scale))
        self.configure(bg=p["surface"], height=h)
        self.icon.configure(bg=p["surface"], fg=p["muted"])
        self.entry.configure(bg=p["surface"], fg=p["text"], insertbackground=p["text"],
                             selectbackground=p["primary"], selectforeground=p["on_primary"])
        self.hint.configure(bg=p["surface"], fg=p["muted"])
        self.update_state()


class LibraryPage(Page):
    persistent = True

    def __init__(self, app, params):
        super().__init__(app, params)
        S = self.S
        self.body = tk.Frame(self, bd=0)
        self.body.pack(fill="both", expand=True)

        head = tk.Frame(self.body, bd=0)
        head.pack(fill="x", pady=(round(20 * S), round(12 * S)))
        self.title = ttk.Label(head, text="Your library", style="Title.TLabel")
        self.title.pack(side="left")
        self.subtitle = ttk.Label(head, text="", style="Muted.TLabel")
        self.subtitle.pack(side="left", padx=(round(12 * S), 0), pady=(round(6 * S), 0))
        self.heads = [head]

        self.toolbar = FlowFrame(self.body, app)
        self.toolbar.pack(fill="x", pady=(0, round(12 * S)))
        self.sync_btn = CButton(self.toolbar, app, text="Sync library", icon="sync", variant="primary",
                                command=app.start_sync)
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *a: app.refresh_library())
        self.search = SearchBox(self.toolbar, app, self.query, "Search your games")

        self.view_group = tk.Frame(self.toolbar, bd=0)
        self.view_btns = {}
        for mode, icon, label in (("grid", "grid", "Grid"), ("list", "list", "List")):
            b = CButton(self.view_group, app, text=label, icon=icon, variant="segment",
                        command=lambda m=mode: app.set_view(m))
            b.pack(side="left")
            self.view_btns[mode] = b

        self.sort_group = tk.Frame(self.toolbar, bd=0)
        self.sort_label = ttk.Label(self.sort_group, text="Sort", style="Muted.TLabel")
        self.sort_label.pack(side="left", padx=(0, round(4 * S)))
        self.sort_btns = {}
        for key, label in app.SORTS:
            b = CButton(self.sort_group, app, text=label, variant="segment",
                        command=lambda k=key: app.set_sort(k))
            b.pack(side="left")
            self.sort_btns[key] = b

        self.filter_group = tk.Frame(self.toolbar, bd=0)
        self.hide_done = tk.BooleanVar()
        self.only_unmatched = tk.BooleanVar()
        self.chip_hide = CButton(self.filter_group, app, text="Hide added", icon="hide", variant="chip",
                                 command=lambda: self.toggle_filter(self.hide_done))
        self.chip_hide.pack(side="left", padx=(0, round(4 * S)))
        self.chip_search = CButton(self.filter_group, app, text="Only search links", icon="filter",
                                   variant="chip", command=lambda: self.toggle_filter(self.only_unmatched))
        self.chip_search.pack(side="left")

        self.toolbar.add(self.sync_btn)
        self.toolbar.add(self.search, expand=True, min_w=200, max_w=520)
        self.toolbar.add(self.view_group, break_after=False)
        self.toolbar.add(self.sort_group)
        self.toolbar.add(self.filter_group)

        self.area = tk.Frame(self.body, bd=0)
        self.banner = Banner(self.body, app, pack_kw={"fill": "x", "pady": (0, round(12 * S)),
                                                      "before": self.area})
        self.area.pack(fill="both", expand=True)
        self.view = GameView(self.area, app)
        self.header = ListHeader(self.area, app, self.view)
        self.scrollbar = ttk.Scrollbar(self.area, orient="vertical", command=self.view.yview)
        self.view.scrollbar = self.scrollbar
        self.view.configure(yscrollcommand=self.view.on_scroll)
        self.scrollbar.pack(side="right", fill="y")
        self.view.pack(side="bottom", fill="both", expand=True)

        foot = tk.Frame(self.body, bd=0)
        foot.pack(fill="x", before=self.area, side="bottom", pady=(round(8 * S), round(12 * S)))
        self.status = ttk.Label(foot, text="", style="Small.TLabel")
        self.status.pack(side="left")
        self.counter = ttk.Label(foot, text="", style="Small.TLabel")
        self.counter.pack(side="right")
        self.heads.append(foot)
        self.groups_frames = [self.body, self.area, self.view_group, self.sort_group, self.filter_group]
        self.retheme()

    def crumbs(self):
        return ["Library"]

    def toggle_filter(self, var):
        var.set(not var.get())
        self.app.refresh_library()

    def capture(self):
        return {"scroll": self.view.yview()[0], "focus": self.view.focus_key}

    def restore(self, state):
        if "scroll" in state:
            self.after(20, lambda: self.view.yview_moveto(state["scroll"]))

    def on_show(self):
        self.app.refresh_library()

    def resized(self, width):
        pad = self.side_pad(width)
        self.body.pack_configure(padx=pad)
        narrow = width < 520 * self.S
        self.sync_btn.set(text="" if narrow else ("Syncing…" if self.app.syncing else "Sync library"))
        for mode, b in self.view_btns.items():
            b.set(text="" if narrow else mode.title())
        self.status.configure(wraplength=max(160, width - 2 * pad - round(120 * self.S)))
        self.toolbar.relayout()
        if width >= 520 * self.S:
            if not self.sort_label.winfo_ismapped():
                self.sort_label.pack(side="left", padx=(0, round(4 * self.S)), before=self.sort_btns["name"])
        else:
            self.sort_label.pack_forget()

    def retheme(self):
        super().retheme()
        bg = self.app.palette["bg"]
        for f in getattr(self, "groups_frames", []) + getattr(self, "heads", []):
            f.configure(bg=bg)


class DetailPage(Page):
    """A game's banner, actions and Steam achievements."""

    def __init__(self, app, params):
        super().__init__(app, params)
        self.game = app.games.get(str(params["appid"]))
        S = self.S
        self.scroll = ScrollFrame(self, app)
        self.scroll.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.scroll.inner, bd=0)
        self.inner.pack(fill="both", expand=True, padx=round(32 * S), pady=(round(20 * S), round(24 * S)))
        self.frames = [self.inner]
        self.icon_labels = []
        self.blank = None
        self.layout = None
        if self.game is None:
            ttk.Label(self.inner, text="This game isn't in your library anymore.",
                      style="Heading.TLabel").pack(anchor="w")
            return
        g = self.game

        self.hero = tk.Frame(self.inner, bd=0)
        self.hero.pack(fill="x")
        self.banner_canvas = tk.Canvas(self.hero, highlightthickness=0, bd=0)
        self.info = tk.Frame(self.hero, bd=0)
        self.frames += [self.hero, self.info]
        self.name = self.wrap(ttk.Label(self.info, text=app.name_of(g), style="Title.TLabel",
                                        justify="left"), 560, 80)
        self.name.pack(anchor="w")

        meta = FlowFrame(self.info, app, gap=16)
        meta.pack(fill="x", pady=(round(8 * S), round(16 * S)))
        for icon, text in (("clock", f"{fmt_playtime(g['playtime'])} played" if g["playtime"] else "Not played yet"),
                           ("calendar", f"Last played {fmt_relative(g['last'])} ({fmt_date(g['last'])})"
                            if g["playtime"] else "Never launched"),
                           ("link", app.link_label(g))):
            item = tk.Frame(meta, bd=0)
            tk.Label(item, text=ICONS[icon], font=app.fonts["icon"], bd=0).pack(side="left", padx=(0, round(6 * S)))
            tk.Label(item, text=text, font=app.fonts["body"], bd=0).pack(side="left")
            meta.add(item)
            self.frames.append(item)

        actions = FlowFrame(self.info, app)
        actions.pack(fill="x")
        self.add_btn = CButton(actions, app, icon="open", variant="primary",
                               command=lambda: app.open_backloggd(g))
        self.mark_btn = CButton(actions, app, icon="check", variant="chip", command=self.toggle_added)
        search_btn = CButton(actions, app, text="Search on Backloggd", icon="search",
                             command=lambda: app.search_backloggd(g))
        store_btn = CButton(actions, app, text="Steam store", icon="store", command=lambda: app.open_store(g))
        for b in (self.add_btn, self.mark_btn, search_btn, store_btn):
            actions.add(b)
        self.actions = actions
        self.update_buttons()

        # Achievements
        sec = tk.Frame(self.inner, bd=0)
        sec.pack(fill="x", pady=(round(32 * S), round(8 * S)))
        self.frames.append(sec)
        ttk.Label(sec, text="Achievements", style="Heading.TLabel").pack(side="left")
        self.refresh_btn = CButton(sec, app, text="Refresh", icon="sync", variant="ghost", compact=True,
                                   command=lambda: self.load(force=True))
        self.refresh_btn.pack(side="right")
        self.ach_banner = Banner(self.inner, app)
        self.summary = tk.Frame(self.inner, bd=0)
        self.summary.pack(fill="x")
        self.frames.append(self.summary)
        self.summary_text = self.wrap(ttk.Label(self.summary, text="", style="Muted.TLabel",
                                                justify="left"), 640, 80)
        self.summary_text.pack(anchor="w")
        self.progress = ttk.Progressbar(self.summary, mode="determinate", maximum=100,
                                        style="Accent.Horizontal.TProgressbar")
        self.list = tk.Frame(self.inner, bd=0)
        self.list.pack(fill="x", pady=(round(12 * S), 0))
        self.frames.append(self.list)
        self.retheme()
        self.load()

    def crumbs(self):
        return ["Library", self.app.name_of(self.game) if self.game else "Game"]

    def capture(self):
        return {"scroll": self.scroll.position()}

    def restore(self, state):
        if "scroll" in state:
            self.scroll.restore(state["scroll"])

    def retheme(self):
        super().retheme()
        p = self.app.palette
        for f in getattr(self, "frames", []):
            if f.winfo_exists():
                f.configure(bg=p["bg"])
                for child in f.winfo_children():
                    if isinstance(child, tk.Label) and not isinstance(child, ttk.Label):
                        child.configure(bg=p["bg"], fg=p["muted"])
        if getattr(self, "banner_canvas", None) is not None:
            self.banner_canvas.configure(bg=p["bg"])
            self.draw_banner()

    def resized(self, width):
        if self.game is None:
            return
        S = self.S
        pad = self.side_pad(width)
        self.inner.pack_configure(padx=pad)
        avail = width - 2 * pad - 16 * S
        layout = "side" if avail >= 820 * S else "stack"
        bw = round(min(460 * S, avail)) // 4 * 4
        size = (max(160, bw), max(75, round(bw * 215 / 460)))
        if layout != self.layout or size != getattr(self, "banner_size", None):
            self.layout, self.banner_size = layout, size
            self.banner_canvas.configure(width=size[0], height=size[1])
            self.banner_canvas.grid_forget()
            self.info.grid_forget()
            if layout == "side":
                self.banner_canvas.grid(row=0, column=0, sticky="nw")
                self.info.grid(row=0, column=1, sticky="nwe", padx=(round(24 * S), 0))
                self.hero.columnconfigure(1, weight=1)
            else:
                self.banner_canvas.grid(row=0, column=0, sticky="nw")
                self.info.grid(row=1, column=0, sticky="nwe", pady=(round(16 * S), 0))
                self.hero.columnconfigure(1, weight=0)
            self.draw_banner()
        info_w = avail - (size[0] + 24 * S if layout == "side" else 0)
        self.name.configure(wraplength=max(160, info_w))
        for lbl in getattr(self, "desc_labels", []):
            if lbl.winfo_exists():
                lbl.configure(wraplength=max(160, avail - 260 * S))

    def update_buttons(self):
        added = self.app.is_added(self.game)
        self.add_btn.set(text="Open on Backloggd" if added else "Add to Backloggd")
        self.mark_btn.set(text="Marked as added" if added else "Mark as added", selected=added)
        self.actions.relayout()

    def toggle_added(self):
        self.app.toggle_added(self.game)
        self.update_buttons()

    def draw_banner(self):
        if not hasattr(self, "banner_size"):
            return
        p, g = self.app.palette, self.game
        w, h = self.banner_size
        r = round(10 * self.S)
        img = self.app.images.get(("banner", g["appid"], self.banner_size),
                                  lambda: core.steam_art(g["appid"], "header"),
                                  self.banner_size, "cover", self._banner_ready, radius=r)
        c = self.banner_canvas
        c.delete("all")
        if img:
            c.create_image(0, 0, image=img, anchor="nw")
        else:
            round_rect(c, 0, 0, w, h, r, fill=p["placeholder"], outline="")
            c.create_text(w / 2, h / 2, text=self.app.name_of(g), fill=p["muted"],
                          font=self.app.fonts["heading"], width=w - 40)

    def _banner_ready(self):
        if self.winfo_exists():
            self.draw_banner()

    # ---- achievements

    def load(self, force=False):
        appid = self.game["appid"]
        cached = None if force else core.load_achievements(appid)
        if cached is not None:
            self.show_achievements(cached)
            return
        steam_id = self.app.library.get("steam_id")
        if not core.config_complete(self.app.cfg) or not steam_id:
            self.set_summary("Sync your Steam library first to see achievements.")
            return
        self.ach_banner.hide()
        self.set_summary("Loading achievements from Steam…", loading=True)
        self.refresh_btn.set(enabled=False)
        cfg = dict(self.app.cfg)
        self.app.jobs.submit(lambda: core.fetch_achievements(cfg, steam_id, appid), self.loaded)

    def set_summary(self, text, loading=False):
        self.summary_text.configure(text=text, style="Muted.TLabel")
        if loading:
            self.progress.configure(mode="indeterminate")
            self.progress.pack(fill="x", pady=(round(8 * self.S), 0))
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def loaded(self, result, error):
        if not self.winfo_exists():
            return
        self.refresh_btn.set(enabled=True)
        self.app.ach_cache.pop(self.game["appid"], None)
        if error is not None:
            msg = str(error) if isinstance(error, core.SyncError) else \
                f"Couldn't load achievements ({type(error).__name__})."
            self.set_summary("")
            self.ach_banner.pack_kw = {"fill": "x", "before": self.summary}
            self.ach_banner.show("error", msg, actions=[("Try again", lambda: self.load(force=True))])
            return
        self.show_achievements(result)

    def show_achievements(self, data):
        for child in self.list.winfo_children():
            child.destroy()
        self.icon_labels = []
        self.desc_labels = []
        items = data.get("achievements", [])
        if not items:
            self.set_summary("This game has no Steam achievements.")
            return
        done = sum(1 for a in items if a["achieved"])
        pct = round(100 * done / len(items))
        self.set_summary("")
        self.summary_text.configure(style="Bold.TLabel",
                                    text=f"{done} of {len(items)} unlocked  ·  {pct}%  ·  "
                                         f"updated {fmt_relative(data.get('fetched_at', 0))}")
        self.progress.configure(mode="determinate", value=pct)
        self.progress.pack(fill="x", pady=(round(8 * self.S), 0))
        for a in items:
            self.add_row(a)
        self.retheme_rows()
        self.resized(self.winfo_width())

    def add_row(self, a):
        S, app = self.S, self.app
        row = tk.Frame(self.list, bd=0)
        row.pack(fill="x")
        size = (round(44 * S), round(44 * S))
        if self.blank is None:
            self.blank = tk.PhotoImage(width=size[0], height=size[1])
        icon = tk.Label(row, image=self.blank, bd=0)
        icon.pack(side="left", anchor="n", pady=round(12 * S))
        self.icon_labels.append(icon)
        url = a["icon"] if a["achieved"] else (a["icon_locked"] or a["icon"])
        if url:
            key = ("ach", url, size)

            def ready(lbl=icon, k=key):
                if lbl.winfo_exists() and k in app.images.cache:
                    lbl.configure(image=app.images.cache[k])

            img = app.images.get(key, lambda u=url: core.url_image(u), size, "contain", ready,
                                 radius=round(6 * S))
            if img:
                icon.configure(image=img)
        right = tk.Frame(row, bd=0)
        right.pack(side="right", anchor="n", pady=round(12 * S), padx=(round(12 * S), 0))
        if a["achieved"]:
            tk.Label(right, text=f"Unlocked {fmt_date(a['unlocked_at'])}", bd=0,
                     font=app.fonts["small_bold"], name="unlocked").pack(anchor="e")
        else:
            tk.Label(right, text="Locked", bd=0, font=app.fonts["small"], name="locked").pack(anchor="e")
        if a.get("percent") is not None:
            tk.Label(right, text=f"{a['percent']:.1f}% of players", bd=0, font=app.fonts["small"],
                     name="pct").pack(anchor="e")
        text = tk.Frame(row, bd=0)
        text.pack(side="left", fill="x", expand=True, padx=(round(14 * S), 0), pady=round(12 * S))
        tk.Label(text, text=a["name"], bd=0, font=app.fonts["body_bold"], anchor="w", justify="left",
                 name="title_on" if a["achieved"] else "title_off").pack(anchor="w")
        if a.get("description"):
            d = tk.Label(text, text=a["description"], bd=0, font=app.fonts["small"], anchor="w",
                         justify="left", name="desc")
            d.pack(anchor="w")
            self.desc_labels.append(d)
        tk.Frame(self.list, bd=0, height=1, name=f"sep{len(self.icon_labels)}").pack(fill="x")

    def retheme_rows(self):
        p = self.app.palette
        colors = {"unlocked": p["accent"], "locked": p["muted"], "pct": p["muted"],
                  "title_on": p["text"], "title_off": p["muted"], "desc": p["muted"]}
        for row in self.list.winfo_children():
            if row.winfo_name().startswith("sep"):
                row.configure(bg=p["border"])
                continue
            row.configure(bg=p["bg"])
            for w in row.winfo_children():
                w.configure(bg=p["bg"])
                for c in w.winfo_children():
                    c.configure(bg=p["bg"], fg=colors.get(c.winfo_name(), p["text"]))


class SetupSession:
    """Values typed during setup, shared by its step pages."""

    STEPS = ("welcome", "steam_key", "steam_profile", "igdb", "done")

    def __init__(self, cfg, origin):
        cfg = cfg or {}
        self.values = {k: cfg.get(k, "") for k in core.CONFIG_KEYS}
        self.origin = origin  # history index to return to when setup is finished
        self.saved = None


class SetupPage(Page):
    """One step of the setup, written for people who have never used an API."""

    def __init__(self, app, params):
        super().__init__(app, params)
        self.session = params["session"]
        self.step = params["step"]
        self.vars = {}
        self.busy = False
        S = self.S
        self.scroll = ScrollFrame(self, app)
        self.scroll.pack(fill="both", expand=True)
        self.body = tk.Frame(self.scroll.inner, bd=0)
        self.body.pack(fill="both", expand=True, padx=round(32 * S), pady=(round(24 * S), round(16 * S)))
        self.frames = [self.body]
        self.status = None
        getattr(self, "step_" + self.step)()
        foot = tk.Frame(self.body, bd=0)
        foot.pack(fill="x", pady=(round(28 * S), 0))
        self.frames.append(foot)
        self.next_btn = CButton(foot, app, text=self.next_text, icon_right="forward", variant="primary",
                                command=self.next)
        self.next_btn.pack(side="left")
        if self.step != "done":
            CButton(foot, app, text="Back", icon="back", command=app.back).pack(side="left", padx=(round(8 * S), 0))
        inner = list(SetupSession.STEPS[1:-1])
        if self.step in inner:
            ttk.Label(foot, text=f"Step {inner.index(self.step) + 1} of {len(inner)}",
                      style="Muted.TLabel").pack(side="right")
        self.retheme()

    def crumbs(self):
        names = {"welcome": "Welcome", "steam_key": "Steam key", "steam_profile": "Steam profile",
                 "igdb": "Exact links", "done": "All set"}
        return ["API keys", names[self.step]]

    def retheme(self):
        super().retheme()
        for f in getattr(self, "frames", []):
            if f.winfo_exists():
                f.configure(bg=self.app.palette["bg"])

    def resized(self, width):
        self.body.pack_configure(padx=self.side_pad(width))

    # ---- building helpers

    def frame(self, **pack):
        f = tk.Frame(self.body, bd=0)
        f.pack(fill="x", **pack)
        self.frames.append(f)
        return f

    def heading(self, text, sub=None):
        ttk.Label(self.body, text=text, style="Title.TLabel").pack(anchor="w")
        if sub:
            self.wrap(ttk.Label(self.body, text=sub, style="Muted.TLabel", justify="left")).pack(
                anchor="w", pady=(round(4 * self.S), 0))
        self.frame(pady=(round(12 * self.S), 0))

    def para(self, text, muted=False, pady=(0, 8)):
        self.wrap(ttk.Label(self.body, text=text, justify="left",
                            style="Muted.TLabel" if muted else "TLabel")).pack(
            anchor="w", pady=tuple(round(v * self.S) for v in pady))

    def numbered(self, n, text):
        row = self.frame(pady=(round(12 * self.S), round(6 * self.S)))
        ttk.Label(row, text=f"{n}", style="Bold.TLabel", width=3).pack(side="left", anchor="n")
        self.wrap(ttk.Label(row, text=text, justify="left"), 600, 110).pack(side="left", anchor="w")

    def indent(self):
        return self.frame(padx=(round(28 * self.S), 0), pady=(0, round(4 * self.S)))

    def link_button(self, text, url):
        CButton(self.indent(), self.app, text=text, icon_right="open",
                command=lambda: webbrowser.open(url)).pack(anchor="w")

    def copy_field(self, value):
        """A read-only box with the text and a Copy button, for pasting into web forms."""
        f = self.indent()
        box = ttk.Entry(f, width=22, font=self.app.fonts["mono"])
        box.insert(0, value)
        box.configure(state="readonly")
        box.pack(side="left")
        btn = CButton(f, self.app, text="Copy", icon="copy")

        def copy():
            self.clipboard_clear()
            self.clipboard_append(value)
            btn.set(text="Copied", icon="check")
            self.after(1600, lambda: btn.winfo_exists() and btn.set(text="Copy", icon="copy"))

        btn.command = copy
        btn.pack(side="left", padx=(round(8 * self.S), 0))

    def input_field(self, key, secret=False, width=44):
        f = self.indent()
        var = tk.StringVar(value=self.session.values.get(key, ""))
        var.trace_add("write", lambda *a: self.session.values.__setitem__(key, var.get().strip()))
        var.trace_add("write", lambda *a: self.on_input())
        self.vars[key] = var
        entry = ttk.Entry(f, textvariable=var, width=width, show="•" if secret else "")
        # Shrinks on narrow windows instead of pushing the Show button out of view
        f.columnconfigure(0, weight=1, minsize=0)
        entry.grid(row=0, column=0, sticky="w")
        f.bind("<Configure>", lambda e: entry.grid_configure(
            sticky="we" if e.width < entry.winfo_reqwidth() + round(120 * self.S) else "w"))
        if secret:
            show = CButton(f, self.app, text="Show", icon="view", variant="chip", compact=True)

            def toggle():
                hidden = entry.cget("show") == "•"
                entry.configure(show="" if hidden else "•")
                show.set(selected=hidden, text="Hide" if hidden else "Show", icon="hide" if hidden else "view")

            show.command = toggle
            show.grid(row=0, column=1, padx=(round(8 * self.S), 0))
        entry.bind("<Return>", lambda e: self.next())
        return entry

    def status_line(self):
        self.status = self.wrap(ttk.Label(self.body, text="", justify="left"))
        self.status.pack(anchor="w", pady=(round(12 * self.S), 0))

    def set_status(self, text, style="TLabel"):
        if self.status is not None:
            self.status.configure(text=text, style=style)

    def on_input(self):
        if self.step == "igdb" and hasattr(self, "next_btn"):
            self.next_btn.set(text=self.igdb_text())

    # ---- steps

    def step_welcome(self):
        self.heading("Welcome to Backloggd Checklist",
                     "Turn your Steam games into a checklist for logging them on Backloggd.")
        self.para("Setup takes about 2 minutes and you only do it once. You need your Steam "
                  "account, nothing else.")
        ttk.Label(self.body, text="Is it safe?", style="Bold.TLabel").pack(anchor="w", pady=(round(12 * self.S), round(4 * self.S)))
        for line in ("The app never asks for your password and never signs in to your accounts.",
                     "It only reads your game list through Steam's official service.",
                     "It never changes anything on Steam or Backloggd: you add games yourself.",
                     "Everything you enter stays on this computer, encrypted."):
            row = self.frame(pady=(0, round(4 * self.S)))
            ttk.Label(row, text=ICONS["check"], style="Icon.TLabel").pack(side="left", padx=(0, round(8 * self.S)))
            self.wrap(ttk.Label(row, text=line, style="Muted.TLabel", justify="left"), 600, 100).pack(side="left")
        self.next_text = "Let's start"

    def step_steam_key(self):
        self.heading("Get your Steam key", "Steam gives you a personal key so this app can read your game list.")
        self.numbered(1, "Open Steam's key page and sign in if Steam asks you to.")
        self.link_button("Open Steam key page", STEAM_KEY_URL)
        self.numbered(2, "Click the “Domain Name” box on that page and paste this:")
        self.copy_field("localhost")
        self.numbered(3, "Tick the box to agree to Steam's terms, then click “Register”.")
        self.numbered(4, "Steam now shows “Key: …”. Copy that key and paste it here:")
        self.after(50, self.input_field("steam_api_key", secret=True).focus_set)
        self.status_line()
        self.para("Steam warns you to never share your key with anyone. That's good advice and it's "
                  "normal: this app keeps the key encrypted on your computer and only uses it to read "
                  "your game list.", muted=True, pady=(12, 4))
        self.para("Steam says you can't get a key? Steam only gives keys to accounts that have spent "
                  "at least $5 in the Steam store.", muted=True)
        self.next_text = "Continue"

    def step_steam_profile(self):
        self.heading("Find your Steam profile", "So the app knows whose games to read.")
        self.numbered(1, "Open your Steam profile, then copy the address from your browser's address "
                         "bar (it starts with https://steamcommunity.com/).")
        self.link_button("Open my Steam profile", STEAM_PROFILE_URL)
        self.numbered(2, "Paste it here:")
        self.after(50, self.input_field("steam_id", width=52).focus_set)
        self.numbered(3, "Make your game list readable: on the privacy page, set “Game details” to “Public”.")
        self.link_button("Open Steam privacy settings", STEAM_PRIVACY_URL)
        self.status_line()
        self.next_text = "Check and continue"

    def step_igdb(self):
        self.heading("Optional: exact Backloggd links",
                     "Without this, each game opens a Backloggd search and you click the right result. "
                     "With it, each game opens its exact Backloggd page. You can skip this and turn it "
                     "on later from API keys.")
        self.para("You need a free Twitch account with two-factor authentication turned on.", muted=True)
        self.numbered(1, "Open Twitch's developer page and sign in.")
        self.link_button("Open Twitch developer page", TWITCH_CREATE_URL)
        self.numbered(2, "Name: type something unique, like “Backloggd Checklist” and your name.")
        self.numbered(3, "OAuth Redirect URLs: paste this, then click “Add”:")
        self.copy_field("http://localhost")
        self.numbered(4, "Category: “Application Integration”. Client Type: “Confidential”. Then click “Create”.")
        self.numbered(5, "Click “Manage” next to your new app. Copy the Client ID and paste it here:")
        self.input_field("igdb_client_id")
        self.numbered(6, "Click “New Secret”, copy it and paste it here:")
        self.input_field("igdb_client_secret", secret=True)
        self.status_line()
        self.next_text = self.igdb_text()

    def igdb_text(self):
        v = self.session.values
        return "Check and continue" if (v["igdb_client_id"] or v["igdb_client_secret"]) else "Skip this step"

    def step_done(self):
        self.heading("All set", "Your settings are saved and encrypted on this computer.")
        v = self.session.values
        if not (v["igdb_client_id"] and v["igdb_client_secret"]):
            self.para("Exact links are off, so games will open a Backloggd search. You can turn them on "
                      "any time from API keys.", muted=True)
        self.para("Next, the app reads your Steam library. Then click “Add to Backloggd” on any game.")
        self.next_text = "Sync my library"

    # ---- moving on

    def go_next(self):
        steps = SetupSession.STEPS
        self.app.navigate("setup", step=steps[steps.index(self.step) + 1], session=self.session)

    def next(self):
        if self.busy:
            return
        v = self.session.values
        if self.step == "steam_key":
            try:
                core.check_steam_key_format(v["steam_api_key"])
            except core.SyncError as e:
                self.set_status(str(e), "Error.TLabel")
                return
            self.go_next()
        elif self.step == "steam_profile":
            self.run_check(lambda: core.check_steam(v["steam_api_key"], v["steam_id"]),
                           lambda r: f"Found {r[1]} games in your Steam library.")
        elif self.step == "igdb":
            if not (v["igdb_client_id"] or v["igdb_client_secret"]):
                self.save()
                self.go_next()
                return
            self.run_check(lambda: core.check_igdb(v["igdb_client_id"], v["igdb_client_secret"]),
                           lambda r: "Twitch accepted your keys. Exact links are on.", then=self.save)
        elif self.step == "done":
            self.app.finish_setup(self.session)
        else:
            self.go_next()

    def save(self):
        cfg = dict(self.session.values)
        if not (cfg["igdb_client_id"] and cfg["igdb_client_secret"]):
            cfg["igdb_client_id"] = cfg["igdb_client_secret"] = ""
        core.save_config(cfg)
        self.session.saved = cfg
        self.app.cfg = cfg

    def run_check(self, fn, ok_text, then=None):
        self.busy = True
        self.next_btn.set(enabled=False)
        self.set_status("Checking…", "Muted.TLabel")

        def done(result, error):
            if not self.winfo_exists():
                return
            self.busy = False
            self.next_btn.set(enabled=True)
            if error is not None:
                msg = str(error) if isinstance(error, core.SyncError) else \
                    f"Something went wrong ({type(error).__name__}). Try again."
                self.set_status(msg, "Error.TLabel")
                return
            self.set_status("✓  " + ok_text(result), "Ok.TLabel")
            if then:
                then()
            self.after(700, lambda: self.winfo_exists() and self.go_next())

        self.app.jobs.submit(fn, done)


class HelpPage(Page):
    SHORTCUTS = (
        ("Alt + ←  /  Alt + →", "Go back / forward (also the mouse side buttons)"),
        ("Tab", "Move between buttons and the game list"),
        ("Arrow keys", "Move between games"),
        ("Enter", "Open the selected game"),
        ("Space", "Mark the selected game as added"),
        ("A", "Open the selected game on Backloggd"),
        ("Ctrl + F", "Search your games"),
        ("F5", "Sync your Steam library"),
        ("Esc", "Go back"),
    )

    def __init__(self, app, params):
        super().__init__(app, params)
        S = self.S
        self.scroll = ScrollFrame(self, app)
        self.scroll.pack(fill="both", expand=True)
        self.body = tk.Frame(self.scroll.inner, bd=0)
        self.body.pack(fill="both", expand=True, padx=round(32 * S), pady=(round(24 * S), round(24 * S)))
        self.frames = [self.body]
        ttk.Label(self.body, text="How to use", style="Title.TLabel").pack(anchor="w")
        self.section("Getting started")
        for i, line in enumerate((
                "Open “API keys” and follow the setup (about 2 minutes, done once).",
                "Click “Sync library”. Your games appear in “Played” and “Not played yet”. "
                "Click a group's title to close or open it.",
                "The app always opens with your most recently played games first. "
                "Choose Grid or List, and sort by name, playtime or last played. Click the active "
                "sort again to flip it. Playtime and Last played: ↓ highest/newest first, ↑ lowest/oldest "
                "first. Name: ↓ A to Z, ↑ Z to A.",
                "Rest the mouse on a cover to see playtime, when you last played and your achievement progress.",
                "Sign in to backloggd.com in your browser, then click “Add to Backloggd” on a game. "
                "Its Backloggd page opens and you add it there yourself.",
                "Tick the check mark on a game when it's done. “Hide added” keeps the list short.",
                "Click a game to see its details and Steam achievements.",
                "If a Backloggd page says “Page not found”, use “Search on Backloggd” on the game's page.",
                "Bought new games? Sync again. Your check marks are kept.",
                "Open “Settings” to change the theme, the color and the text size."), 1):
            row = self.row()
            ttk.Label(row, text=f"{i}", style="Bold.TLabel", width=3).pack(side="left", anchor="n")
            self.wrap(ttk.Label(row, text=line, justify="left"), 680, 110).pack(side="left", anchor="w")
        self.section("Keyboard shortcuts")
        for keys, what in self.SHORTCUTS:
            row = self.row()
            ttk.Label(row, text=keys, style="Bold.TLabel", width=22).pack(side="left", anchor="n")
            self.wrap(ttk.Label(row, text=what, style="Muted.TLabel", justify="left"), 520, 300).pack(side="left")
        self.section("Your safety")
        for line in ("The app never asks for a password and never logs in to any account.",
                     "It only uses Steam's and IGDB's official services.",
                     "It never sends anything to Backloggd: you add every game yourself.",
                     "Your keys are encrypted with your Windows account and stored only on this computer."):
            row = self.row()
            ttk.Label(row, text=ICONS["check"], style="Icon.TLabel").pack(side="left", padx=(0, round(10 * S)))
            self.wrap(ttk.Label(row, text=line, style="Muted.TLabel", justify="left"), 680, 110).pack(side="left")
        self.retheme()

    def crumbs(self):
        return ["Help"]

    def section(self, title):
        ttk.Label(self.body, text=title, style="Heading.TLabel").pack(
            anchor="w", pady=(round(28 * self.S), round(8 * self.S)))

    def row(self):
        f = tk.Frame(self.body, bd=0)
        f.pack(fill="x", pady=(round(4 * self.S), round(4 * self.S)))
        self.frames.append(f)
        return f

    def capture(self):
        return {"scroll": self.scroll.position()}

    def restore(self, state):
        if "scroll" in state:
            self.scroll.restore(state["scroll"])

    def resized(self, width):
        self.body.pack_configure(padx=self.side_pad(width))

    def retheme(self):
        super().retheme()
        for f in getattr(self, "frames", []):
            f.configure(bg=self.app.palette["bg"])


class SettingsPage(Page):
    """Appearance: theme, color and text size. API keys have their own page."""

    def __init__(self, app, params):
        super().__init__(app, params)
        S = self.S
        self.scroll = ScrollFrame(self, app)
        self.scroll.pack(fill="both", expand=True)
        self.body = tk.Frame(self.scroll.inner, bd=0)
        self.body.pack(fill="both", expand=True, padx=round(32 * S), pady=(round(24 * S), round(24 * S)))
        self.frames = [self.body]
        ttk.Label(self.body, text="Settings", style="Title.TLabel").pack(anchor="w")

        self.section("Theme", "Light, dark, or the same as your Windows setting.")
        row = self.row()
        for mode, icon, label in (("system", "auto", "Same as Windows"), ("light", "sun", "Light"),
                                  ("dark", "moon", "Dark")):
            CButton(row, app, text=label, icon=icon, variant="segment", selected=app.theme_mode == mode,
                    command=lambda m=mode: app.set_theme(m)).pack(side="left", padx=(0, round(4 * S)))

        self.section("Color", "Used for buttons, highlights and the selected sort.")
        row = self.row()
        for key, name in theme.ACCENT_NAMES:
            cell = tk.Frame(row, bd=0)
            cell.pack(side="left", padx=(0, round(12 * S)))
            self.frames.append(cell)
            sw = Swatch(cell, app, key, lambda k=key: app.set_accent(k))
            sw.selected = app.accent == key
            sw.redraw()
            sw.pack()
            ttk.Label(cell, text=name, style="Bold.TLabel" if app.accent == key else "Small.TLabel").pack(
                pady=(round(4 * S), 0))

        steps = theme.FONT_SCALES
        current = min(steps, key=lambda v: abs(v - app.font_scale))
        i = steps.index(current)
        self.section("Text size", "Makes all text in the app smaller or larger, from half size to double size.")
        row = self.row()
        smaller = CButton(row, app, text="Smaller", icon="zoom_out",
                          command=lambda: app.set_font_scale(steps[i - 1]))
        smaller.pack(side="left")
        smaller.set(enabled=i > 0)
        ttk.Label(row, text=f"{round(current * 100)}%", style="Heading.TLabel", width=5,
                  anchor="center").pack(side="left", padx=round(12 * S))
        bigger = CButton(row, app, text="Larger", icon="zoom_in",
                         command=lambda: app.set_font_scale(steps[i + 1]))
        bigger.pack(side="left")
        bigger.set(enabled=i < len(steps) - 1)
        reset = CButton(row, app, text="Reset", variant="ghost", command=lambda: app.set_font_scale(1.0))
        reset.pack(side="left", padx=(round(8 * S), 0))
        reset.set(enabled=current != 1.0)
        if current < 0.75:
            self.wrap(ttk.Label(self.body, text="Very small text can be hard to read.",
                                style="Muted.TLabel")).pack(anchor="w", pady=(round(8 * S), 0))

        self.section("API keys", "Your Steam key and the optional IGDB keys have their own page.")
        row = self.row()
        CButton(row, app, text="Open API keys", icon="key",
                command=lambda: app.open_api_keys(step="steam_key")).pack(side="left")
        self.retheme()

    def crumbs(self):
        return ["Settings"]

    def section(self, title, text):
        ttk.Label(self.body, text=title, style="Heading.TLabel").pack(
            anchor="w", pady=(round(28 * self.S), round(2 * self.S)))
        self.wrap(ttk.Label(self.body, text=text, style="Muted.TLabel", justify="left")).pack(
            anchor="w", pady=(0, round(10 * self.S)))

    def row(self):
        f = tk.Frame(self.body, bd=0)
        f.pack(fill="x", anchor="w")
        self.frames.append(f)
        return f

    def capture(self):
        return {"scroll": self.scroll.position()}

    def restore(self, state):
        if "scroll" in state:
            self.scroll.restore(state["scroll"])

    def resized(self, width):
        self.body.pack_configure(padx=self.side_pad(width))

    def retheme(self):
        super().retheme()
        for f in getattr(self, "frames", []):
            if f.winfo_exists():
                f.configure(bg=self.app.palette["bg"])


PAGES = {"library": LibraryPage, "details": DetailPage, "setup": SetupPage, "help": HelpPage,
         "settings": SettingsPage}


# ---------------------------------------------------------------- main window

class PageSlide:
    """Slides a page in from the side over the shared transition time."""

    def __init__(self, page, start):
        self.page, self.start, self.t = page, start, 0.0

    def step(self, dt):
        self.t = approach(self.t, 1.0, dt)
        if self.page.winfo_exists():
            self.page.place_configure(x=round(self.start * (1 - ease(self.t))))
        return self.t < 1.0


class App(tk.Tk):
    # Games with no playtime were never played (a recent date there only means a recent purchase)
    GROUPS = (("grp:played", "Played", lambda g: g["playtime"] > 0),
              ("grp:unplayed", "Not played yet", lambda g: g["playtime"] == 0))
    SORTS = (("name", "Name"), ("playtime", "Playtime"), ("last", "Last played"))

    def __init__(self):
        super().__init__()
        self.core = core
        self.title("Backloggd Checklist")
        # Next to the script, or inside the bundle when packaged with PyInstaller
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "icon.ico"
        if icon.exists():
            self.iconbitmap(default=str(icon))
        self.scale = self.winfo_fpixels("1i") / 96
        S = self.scale
        self.geometry(f"{round(1180 * S)}x{round(780 * S)}")
        self.minsize(round(360 * S), round(480 * S))

        self.cfg = core.load_config()
        self.library = core.load_library()
        self.done = core.load_done()
        self.games = {str(g["appid"]): g for g in self.library["games"]}
        self.ui = core.load_ui()
        self.collapsed = set(self.ui.get("collapsed", []))
        self.view_mode = self.ui.get("view", "grid")
        self.theme_mode = self.ui.get("theme", "system")
        self.accent = self.ui.get("accent", "pink")
        self.font_scale = self.ui.get("font_scale", 1.0)
        # Every start opens on the most recently played games; the sort can still be changed after
        self.sort_key = "last"
        self.sort_desc = True
        self.ach_cache = {}
        self.syncing = False

        self.themed = weakref.WeakSet()
        self.fonts = theme.fonts(self, self.font_scale)
        self.animator = Animator(self)
        self.jobs = Jobs(self)
        self.images = ImageLoader(self.jobs)
        self.is_dark = theme.resolve(self.theme_mode) == "dark"
        self.palette = theme.palette("dark" if self.is_dark else "light", self.accent)
        theme.apply(self, self.palette, self.fonts)

        self._build_topbar()
        self.content = tk.Frame(self, bd=0)
        self.content.pack(fill="both", expand=True)
        self.menu = tk.Menu(self, tearoff=False)

        self.history = []
        self.index = -1
        self.page = None
        self.library_page = None
        self._bind_keys()
        self.apply_theme()
        self.navigate("library")
        self.after(150, lambda: theme.set_titlebar(self, self.is_dark))
        if not core.config_complete(self.cfg):
            self.after(200, lambda: self.open_api_keys(step="welcome"))

    # ---- top bar

    def _build_topbar(self):
        S = self.scale
        self.topbar = tk.Frame(self, bd=0)
        self.topbar.pack(fill="x")
        inner = tk.Frame(self.topbar, bd=0)
        inner.pack(fill="x", padx=round(12 * S), pady=round(6 * S))
        self.top_inner = inner
        self.back_btn = CButton(inner, self, icon="back", variant="ghost", command=self.back, label="Back")
        self.back_btn.pack(side="left")
        self.fwd_btn = CButton(inner, self, icon="forward", variant="ghost", command=self.forward,
                               label="Forward")
        self.fwd_btn.pack(side="left")
        self.crumb_frame = tk.Frame(inner, bd=0)
        self.settings_btn = CButton(inner, self, text="Settings", icon="settings", variant="ghost",
                                    command=lambda: self.navigate("settings"))
        self.settings_btn.pack(side="right")
        self.keys_btn = CButton(inner, self, text="API keys", icon="key", variant="ghost",
                                command=lambda: self.open_api_keys(step="steam_key"))
        self.keys_btn.pack(side="right")
        self.help_btn = CButton(inner, self, text="Help", icon="help", variant="ghost",
                                command=lambda: self.navigate("help"))
        self.help_btn.pack(side="right")
        self.crumb_frame.pack(side="left", fill="x", expand=True, padx=(round(10 * S), round(8 * S)))
        self.topline = tk.Frame(self, bd=0, height=1)
        self.topline.pack(fill="x")
        self.topbar.bind("<Configure>", lambda e: self.topbar_responsive(e.width))

    def topbar_responsive(self, width):
        narrow = width < 640 * self.scale
        for b, text in ((self.settings_btn, "Settings"), (self.keys_btn, "API keys"),
                        (self.help_btn, "Help")):
            b.set(text="" if narrow else text)
        self.after_idle(self.render_crumbs)

    def render_crumbs(self):
        for w in self.crumb_frame.winfo_children():
            w.destroy()
        if self.page is None:
            return
        p, f = self.palette, self.fonts
        crumbs = self.page.crumbs()
        used = sum(b.winfo_reqwidth() for b in (self.back_btn, self.fwd_btn, self.settings_btn,
                                                  self.keys_btn, self.help_btn))
        avail = max(60, self.topbar.winfo_width() - used - round(48 * self.scale))
        for i, name in enumerate(crumbs):
            last = i == len(crumbs) - 1
            if i:
                tk.Label(self.crumb_frame, text=ICONS["chev_right"], font=f["icon"], bd=0,
                         bg=p["bg"], fg=p["muted"]).pack(side="left", padx=round(6 * self.scale))
            text = fit_text(f["body_bold" if last else "body"], name, avail * (0.6 if last else 0.3))
            lbl = tk.Label(self.crumb_frame, text=text, bd=0, bg=p["bg"],
                           fg=p["text"] if last else p["muted"], font=f["body_bold" if last else "body"],
                           cursor="" if last or name != "Library" else "hand2")
            lbl.pack(side="left")
            if not last and name == "Library":
                lbl.bind("<Button-1>", lambda e: self.navigate("library"))

    # ---- navigation

    def _bind_keys(self):
        self.bind_all("<Alt-Left>", lambda e: self.back())
        self.bind_all("<Alt-Right>", lambda e: self.forward())
        # Tk on Windows reports the mouse side buttons (XButton1/2) as buttons 4 and 5
        if sys.platform == "win32":
            self.bind_all("<Button-4>", lambda e: self.back())
            self.bind_all("<Button-5>", lambda e: self.forward())
        self.bind_all("<BackSpace>", self._backspace)
        self.bind_all("<Escape>", lambda e: self.back() if not isinstance(self.focus_get(), (tk.Entry, ttk.Entry)) else None)
        self.bind_all("<Control-f>", lambda e: self.focus_search())
        self.bind_all("<F5>", lambda e: self.start_sync())
        for key in ("Prior", "Next"):
            self.bind_all(f"<{key}>", lambda e, k=key: self._page_key(k))

    def _backspace(self, event):
        if not isinstance(event.widget, (tk.Entry, ttk.Entry)):
            self.back()

    def _page_key(self, key):
        scroll = getattr(self.page, "scroll", None)
        if isinstance(scroll, ScrollFrame):
            scroll.scroll_by(10 if key == "Next" else -10)

    def navigate(self, name, **params):
        if self.page is not None and 0 <= self.index < len(self.history):
            self.history[self.index]["state"] = self.page.capture()
        self.history = self.history[:self.index + 1]
        self.history.append({"page": name, "params": params, "state": {}})
        self.index += 1
        self.show_entry(direction=1)

    def back(self):
        if self.index > 0:
            self.history[self.index]["state"] = self.page.capture()
            self.index -= 1
            self.show_entry(direction=-1)
        return "break"

    def forward(self):
        if self.index < len(self.history) - 1:
            self.history[self.index]["state"] = self.page.capture()
            self.index += 1
            self.show_entry(direction=1)
        return "break"

    def show_entry(self, direction=1, animate=True):
        entry = self.history[self.index]
        old = self.page
        if old is not None:
            old.place_forget()
            if not old.persistent:
                old.destroy()
        if entry["page"] == "library":
            if self.library_page is None:
                self.library_page = LibraryPage(self, {})
            page = self.library_page
        else:
            page = PAGES[entry["page"]](self, entry["params"])
        self.page = page
        start = round(28 * self.scale) * direction if animate else 0
        page.place(x=start, y=0, relwidth=1, relheight=1)
        page.lift()
        page.restore(entry.get("state", {}))
        page.on_show()
        if animate:
            self.animator.start(PageSlide(page, start))
        self.back_btn.set(enabled=self.index > 0)
        self.fwd_btn.set(enabled=self.index < len(self.history) - 1)
        self.render_crumbs()

    def open_api_keys(self, step="steam_key"):
        if self.page is not None and isinstance(self.page, SetupPage):
            return
        origin = self.index
        self.navigate("setup", step=step, session=SetupSession(self.cfg, origin))

    def finish_setup(self, session):
        if session.saved:
            self.cfg = session.saved
        # Leave the setup steps out of the history: Back from the library shouldn't reopen them
        self.history[self.index]["state"] = {}
        self.history = self.history[:session.origin + 1]
        self.index = session.origin
        if self.history[self.index]["page"] != "library":
            self.history.append({"page": "library", "params": {}, "state": {}})
            self.index += 1
        self.show_entry(direction=-1)
        self.start_sync()

    def focus_search(self):
        if not isinstance(self.page, LibraryPage):
            self.navigate("library")
        self.library_page.search.entry.focus_set()
        return "break"

    # ---- helpers used by the pages and the game view

    def name_of(self, g):
        return g["igdb_name"] or g["steam_name"]

    def is_added(self, g):
        return str(g["appid"]) in self.done

    def link_label(self, g):
        return "Exact Backloggd page" if g["slug"] else "Opens a Backloggd search"

    fmt_playtime = staticmethod(fmt_playtime)

    def fmt_last(self, g):
        # Unplayed games: Steam's date is the purchase, not a play session
        return fmt_date(g["last"]) if g["playtime"] else "—"

    def fmt_relative(self, g):
        return fmt_relative(g["last"])

    def achievement_summary(self, appid):
        """(unlocked, total) from cached achievements only: hovering never downloads."""
        if appid not in self.ach_cache:
            data = core.load_achievements(appid)
            items = (data or {}).get("achievements") or []
            self.ach_cache[appid] = (sum(1 for a in items if a["achieved"]), len(items)) if items else None
        return self.ach_cache[appid]

    def sort_icon(self, key):
        """Playtime / Last played: ↓ highest/newest first, ↑ lowest/oldest first.
        Name is the other way round: ↓ A→Z, ↑ Z→A."""
        if key == "name":
            return "up" if self.sort_desc else "down"
        return "down" if self.sort_desc else "up"

    def empty_state(self):
        if not core.config_complete(self.cfg):
            return {"icon": "key", "title": "Let's set up the app",
                    "text": "Connect your Steam library in about 2 minutes. No passwords needed.",
                    "action": ("Start setup", lambda: self.open_api_keys(step="welcome"))}
        if self.syncing and not self.games:
            return {"icon": "sync", "title": "Loading your Steam library…",
                    "text": "This usually takes a few seconds. Big libraries can take a minute."}
        if not self.games:
            return {"icon": "library", "title": "No games yet",
                    "text": "Sync to load the games from your Steam account.",
                    "action": ("Sync Steam library", self.start_sync)}
        return {"icon": "search", "title": "No games match",
                "text": "Try a different search, or turn off the filters.",
                "action": ("Clear filters", self.clear_filters)}

    # ---- state changes

    def save_ui(self):
        self.ui.update({"collapsed": sorted(self.collapsed), "view": self.view_mode,
                        "theme": self.theme_mode, "sort": self.sort_key, "sort_desc": self.sort_desc,
                        "accent": self.accent, "font_scale": self.font_scale})
        core.save_ui(self.ui)

    def set_sort(self, key):
        if key == self.sort_key:
            self.sort_desc = not self.sort_desc
        else:
            # Most played / most recent first feels natural; names start at A
            self.sort_key, self.sort_desc = key, key != "name"
        self.save_ui()
        self.refresh_library()

    def set_view(self, mode):
        if mode != self.view_mode:
            self.view_mode = mode
            self.save_ui()
            self.library_page.view.yview_moveto(0)
            self.refresh_library()

    def set_theme(self, mode):
        self.theme_mode = mode
        self.save_ui()
        self.apply_theme()

    def set_accent(self, accent):
        self.accent = accent
        self.save_ui()
        self.apply_theme()

    def set_font_scale(self, factor):
        self.font_scale = factor
        theme.resize_fonts(self, self.fonts, factor)
        self.save_ui()
        self.apply_theme()

    def apply_theme(self):
        self.is_dark = theme.resolve(self.theme_mode) == "dark"
        self.palette = theme.palette("dark" if self.is_dark else "light", self.accent)
        theme.apply(self, self.palette, self.fonts)
        p = self.palette
        self.configure(bg=p["bg"])
        for w in (self.topbar, self.top_inner, self.crumb_frame, self.content):
            w.configure(bg=p["bg"])
        self.topline.configure(bg=p["border"])
        self.menu.configure(bg=p["surface"], fg=p["text"], activebackground=p["primary"],
                            activeforeground=p["on_primary"])
        for w in list(self.themed):
            try:
                w.retheme()
            except tk.TclError:
                pass
        theme.set_titlebar(self, self.is_dark)
        if self.page is not None and not self.page.persistent:
            # Rebuilt pages pick up the new colors everywhere; keep their scroll position
            self.history[self.index]["state"] = self.page.capture()
            self.show_entry(animate=False)
        self.render_crumbs()
        self.refresh_library()

    def toggle_group(self, gid):
        self.collapsed.symmetric_difference_update({gid})
        self.save_ui()
        self.refresh_library()

    def toggle_added(self, g):
        self.done.symmetric_difference_update({str(g["appid"])})
        core.save_done(self.done)
        self.refresh_library()

    def clear_filters(self):
        lp = self.library_page
        lp.query.set("")
        lp.hide_done.set(False)
        lp.only_unmatched.set(False)
        self.refresh_library()

    def open_backloggd(self, g):
        webbrowser.open(core.backloggd_url(g))

    def search_backloggd(self, g):
        webbrowser.open(core.backloggd_search_url(g))

    def open_store(self, g):
        webbrowser.open(f"https://store.steampowered.com/app/{g['appid']}/")

    def open_details(self, g):
        self.navigate("details", appid=g["appid"])

    def show_menu(self, g, x, y):
        m = self.menu
        m.delete(0, "end")
        m.add_command(label="Details and achievements", command=lambda: self.open_details(g))
        m.add_command(label="Open on Backloggd" if self.is_added(g) else "Add to Backloggd",
                      command=lambda: self.open_backloggd(g))
        m.add_command(label="Search on Backloggd", command=lambda: self.search_backloggd(g))
        m.add_separator()
        m.add_command(label="Mark as not added" if self.is_added(g) else "Mark as added",
                      command=lambda: self.toggle_added(g))
        m.add_command(label="Open in Steam store", command=lambda: self.open_store(g))
        m.tk_popup(x, y)

    # ---- library list

    def visible_games(self):
        lp = self.library_page
        q = lp.query.get().strip().lower()
        out = []
        for appid, g in self.games.items():
            if q and q not in self.name_of(g).lower() and q not in g["steam_name"].lower():
                continue
            if lp.hide_done.get() and appid in self.done:
                continue
            if lp.only_unmatched.get() and g["slug"]:
                continue
            out.append(g)
        return out

    def sorted_games(self, games, played):
        games.sort(key=lambda g: self.name_of(g).lower(), reverse=self.sort_key == "name" and self.sort_desc)
        if self.sort_key == "playtime" and played:
            games.sort(key=lambda g: g["playtime"], reverse=self.sort_desc)
        elif self.sort_key == "last":
            # For unplayed games this orders by purchase date
            games.sort(key=lambda g: g["last"], reverse=self.sort_desc)
        return games

    def refresh_library(self):
        lp = self.library_page
        if lp is None:
            return
        for key, label in self.SORTS:
            active = key == self.sort_key
            lp.sort_btns[key].set(text=label, selected=active,
                                  icon_right=self.sort_icon(key) if active else None)
        for mode, b in lp.view_btns.items():
            b.set(selected=mode == self.view_mode)
        lp.chip_hide.set(selected=lp.hide_done.get())
        lp.chip_search.set(selected=lp.only_unmatched.get())
        lp.toolbar.relayout()
        if self.view_mode == "list":
            lp.header.pack(side="top", fill="x", before=lp.view)
            lp.header.render()
        else:
            lp.header.pack_forget()

        games = self.visible_games()
        groups = []
        for gid, title, belongs in self.GROUPS:
            members = self.sorted_games([g for g in games if belongs(g)], gid == "grp:played")
            if members:
                groups.append((gid, title, members, gid not in self.collapsed))
        lp.view.set_data(groups, self.view_mode)

        total = len(self.games)
        added = len(self.done & self.games.keys())
        lp.subtitle.configure(text=f"{total} games · {added} added" if total else "")
        lp.counter.configure(text=f"Showing {len(games)} of {total}" if total and len(games) != total else "")
        if not self.syncing:
            lp.status.configure(text=self.last_sync_text())

    def last_sync_text(self):
        ts = self.library.get("synced_at")
        if not ts:
            return "Not synced yet"
        text = f"Synced {fmt_relative(ts)}"
        if not core.igdb_enabled(self.cfg):
            return text + " · Exact Backloggd links are off (optional, see API keys)"
        matched = sum(1 for g in self.games.values() if g["slug"])
        return text + f" · {matched} of {len(self.games)} games have an exact Backloggd link"

    # ---- sync (background thread through Jobs; progress shown inline, never in a pop-up)

    def start_sync(self):
        if self.syncing:
            return
        if not core.config_complete(self.cfg):
            self.open_api_keys(step="welcome")
            return
        if not isinstance(self.page, LibraryPage):
            self.navigate("library")
        lp = self.library_page
        self.syncing = True
        lp.sync_btn.set(enabled=False)
        lp.resized(lp.winfo_width())
        lp.banner.show("info", "Syncing your Steam library…", progress=True, closable=False)
        self.refresh_library()
        cfg = dict(self.cfg)
        before = len(self.games)

        self.sync_msg = None

        def progress(msg):  # called on a worker thread: just store it
            self.sync_msg = msg

        def show_progress():
            if self.syncing:
                if self.sync_msg:
                    lp.banner.msg.configure(text=self.sync_msg)
                self.after(150, show_progress)

        show_progress()

        def done(lib, error):
            self.syncing = False
            lp.sync_btn.set(enabled=True)
            lp.resized(lp.winfo_width())
            if error is not None:
                msg = str(error) if isinstance(error, core.SyncError) else \
                    f"Something went wrong ({type(error).__name__}). Try again."
                lp.banner.show("error", msg, actions=[("Try again", self.start_sync),
                                                      ("Open API keys", lambda: self.open_api_keys())])
                self.refresh_library()
                return
            self.library = lib
            self.games = {str(g["appid"]): g for g in lib["games"]}
            self.ach_cache.clear()
            new = len(self.games) - before
            extra = f", {new} new" if before and new > 0 else ""
            lp.banner.show("success", f"Library synced: {len(self.games)} games{extra}.")
            self.after(6000, lambda: lp.banner.kind == "success" and lp.banner.hide())
            self.refresh_library()

        self.jobs.submit(lambda: core.sync_library(cfg, progress=progress), done)


def main():
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
