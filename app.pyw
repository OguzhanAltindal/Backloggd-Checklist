"""Backloggd Checklist: desktop app.

Run by double-clicking this file, or with:  pythonw app.pyw
"""

import queue
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import checklist_core as core
import theme
from widgets import GameView, ImageLoader, Jobs, ListHeader, ScrollFrame, Tooltip

STEAM_KEY_URL = "https://steamcommunity.com/dev/apikey"
STEAM_PROFILE_URL = "https://steamcommunity.com/my/profile"
STEAM_PRIVACY_URL = "https://steamcommunity.com/my/edit/settings"
TWITCH_CREATE_URL = "https://dev.twitch.tv/console/apps/create"

HELP_TEXT = """\
1. Click “Settings” to run the setup (about 2 minutes, done once).
2. Click “Sync Steam library”. Your games appear in two groups,
   “Played” and “Not played yet”. Click a group's title to close or open it.
3. Switch between Grid and List at the top right. Sort by name, playtime
   or last played; click the same sort again to flip the order (▲ / ▼).
4. Rest the mouse on a game to see its playtime and when you last played it.
5. Sign in to backloggd.com in your browser as usual.
6. Click “Add to Backloggd” on a game: its Backloggd page opens in your
   browser, where you add it yourself.
7. Tick the check box on a game to mark it as added. “Hide added” keeps
   the list short.
8. Click a game itself to see its details and Steam achievements.
9. If a Backloggd page shows “Page not found”, right-click the game and
   choose “Search on Backloggd”.
10. Bought new games? Click “Sync Steam library” again. Your marks are kept.

Your safety:
• The app never asks for a password and never logs in to any account.
• It only uses Steam's and IGDB's official services.
• It never sends anything to Backloggd: you add every game yourself.
• Your keys are encrypted with your Windows account and stored only on this computer."""


def fmt_playtime(m):
    if not m:
        return "Not played"
    h, mm = divmod(m, 60)
    return f"{h}h {mm}m" if h else f"{mm}m"


def fmt_date(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "—"


def show_modal(dialog, master):
    """Center a dialog over its parent window, then make it modal."""
    dialog.withdraw()
    dialog.update_idletasks()
    x = master.winfo_rootx() + (master.winfo_width() - dialog.winfo_reqwidth()) // 2
    y = master.winfo_rooty() + (master.winfo_height() - dialog.winfo_reqheight()) // 3
    dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    dialog.deiconify()
    theme.set_titlebar(dialog, master.is_dark)
    dialog.grab_set()
    dialog.wait_visibility()
    dialog.focus_force()


# ---------------------------------------------------------------- setup wizard

class SetupWizard(tk.Toplevel):
    """Step-by-step setup written for people who have never used an API."""

    def __init__(self, master, cfg, start=0):
        super().__init__(master)
        self.app = master
        self.title("Setup")
        self.transient(master)
        self.resizable(False, False)
        self.configure(bg=master.palette["bg"])
        self.wrap = round(540 * master.scale)
        self.result = None
        self.sync_now = False
        self.events = queue.Queue()
        self.busy = False
        self.status = None
        cfg = cfg or {}
        self.vars = {k: tk.StringVar(value=cfg.get(k, "")) for k in core.CONFIG_KEYS}
        for key in ("igdb_client_id", "igdb_client_secret"):
            self.vars[key].trace_add("write", lambda *a: self.update_igdb_button())

        self.steps = [self.step_welcome, self.step_steam_key, self.step_steam_profile,
                      self.step_igdb, self.step_done]
        self.index = start

        self.body = ttk.Frame(self, padding=(24, 20, 24, 8))
        self.body.pack(fill="both", expand=True)
        ttk.Separator(self).pack(fill="x")
        footer = ttk.Frame(self, padding=(24, 12))
        footer.pack(fill="x")
        self.step_label = ttk.Label(footer, style="Muted.TLabel")
        self.step_label.pack(side="left")
        self.next_btn = ttk.Button(footer, command=self.next, style="Accent.TButton")
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(footer, text="Back", command=self.back)
        self.back_btn.pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda e: self.destroy())
        self.show()
        show_modal(self, master)

    # ---- page building helpers

    def heading(self, text, sub=None):
        ttk.Label(self.body, text=text, style="Title.TLabel").pack(anchor="w")
        if sub:
            ttk.Label(self.body, text=sub, style="Muted.TLabel", wraplength=self.wrap,
                      justify="left").pack(anchor="w", pady=(2, 0))
        ttk.Frame(self.body, height=14).pack()

    def para(self, text, muted=False, pady=(0, 8)):
        ttk.Label(self.body, text=text, wraplength=self.wrap, justify="left",
                  style="Muted.TLabel" if muted else "TLabel").pack(anchor="w", pady=pady)

    def numbered(self, n, text):
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(6, 4))
        ttk.Label(row, text=f"{n}.", width=3, style="Bold.TLabel").pack(side="left", anchor="n")
        ttk.Label(row, text=text, wraplength=self.wrap - 30, justify="left").pack(side="left", anchor="w")

    def indent(self):
        frame = ttk.Frame(self.body)
        frame.pack(fill="x", padx=(28, 0), pady=(0, 4))
        return frame

    def link_button(self, text, url):
        ttk.Button(self.indent(), text=text + "  ↗",
                   command=lambda: webbrowser.open(url)).pack(anchor="w")

    def copy_field(self, value):
        """A read-only box with the text and a Copy button, for pasting into web forms."""
        frame = self.indent()
        box = ttk.Entry(frame, width=24, font=self.app.fonts["mono"])
        box.insert(0, value)
        box.configure(state="readonly")
        box.pack(side="left")
        btn = ttk.Button(frame, text="Copy")
        btn.pack(side="left", padx=(8, 0))

        def copy():
            self.clipboard_clear()
            self.clipboard_append(value)
            btn.configure(text="Copied ✓")
            self.after(1500, lambda: btn.winfo_exists() and btn.configure(text="Copy"))

        btn.configure(command=copy)

    def input_field(self, key, secret=False, width=44):
        frame = self.indent()
        entry = ttk.Entry(frame, textvariable=self.vars[key], width=width, show="•" if secret else "")
        entry.pack(side="left")
        if secret:
            shown = tk.BooleanVar()
            ttk.Checkbutton(frame, text="Show", variable=shown,
                            command=lambda: entry.configure(show="" if shown.get() else "•")
                            ).pack(side="left", padx=(8, 0))
        entry.bind("<Return>", lambda e: self.next())
        return entry

    def status_line(self):
        self.status = ttk.Label(self.body, text="", wraplength=self.wrap, justify="left")
        self.status.pack(anchor="w", pady=(10, 0))

    def set_status(self, text, style="TLabel"):
        self.status.configure(text=text, style=style)

    # ---- steps (each builds its page and returns the Next button text)

    def step_welcome(self):
        self.heading("Welcome to Backloggd Checklist",
                     "Turn your Steam games into a checklist for logging them on Backloggd.")
        self.para("Setup takes about 2 minutes and you only do it once. You need your Steam "
                  "account, nothing else.")
        self.para("Is it safe?", pady=(8, 2))
        for line in ("• The app never asks for your password and never signs in to your accounts.",
                     "• It only reads your game list through Steam's official service.",
                     "• It never changes anything on Steam or Backloggd: you add games yourself.",
                     "• Everything you enter stays on this computer, encrypted."):
            self.para(line, muted=True, pady=(0, 2))
        return "Let's start"

    def step_steam_key(self):
        self.heading("Get your Steam key",
                     "Steam gives you a personal key so this app can read your game list.")
        self.numbered(1, "Open Steam's key page and sign in if Steam asks you to.")
        self.link_button("Open Steam key page", STEAM_KEY_URL)
        self.numbered(2, "Click the “Domain Name” box on that page and paste this:")
        self.copy_field("localhost")
        self.numbered(3, "Tick the box to agree to Steam's terms, then click “Register”.")
        self.numbered(4, "Steam now shows “Key: …”. Copy that key and paste it here:")
        self.input_field("steam_api_key", secret=True).focus_set()
        self.status_line()
        self.para("Steam warns you to never share your key with anyone. That's good advice and "
                  "it's normal: this app keeps the key encrypted on your computer and only uses "
                  "it to read your game list.", muted=True, pady=(10, 4))
        self.para("Steam says you can't get a key? Steam only gives keys to accounts that have "
                  "spent at least $5 in the Steam store.", muted=True)
        return "Next"

    def step_steam_profile(self):
        self.heading("Find your Steam profile", "So the app knows whose games to read.")
        self.numbered(1, "Open your Steam profile, then copy the address from your browser's "
                         "address bar (it starts with https://steamcommunity.com/).")
        self.link_button("Open my Steam profile", STEAM_PROFILE_URL)
        self.numbered(2, "Paste it here:")
        self.input_field("steam_id", width=52).focus_set()
        self.numbered(3, "Make your game list readable: on the privacy page, set "
                         "“Game details” to “Public”.")
        self.link_button("Open Steam privacy settings", STEAM_PRIVACY_URL)
        self.status_line()
        return "Check and continue"

    def step_igdb(self):
        self.heading("Optional: exact Backloggd links",
                     "Without this, each game opens a Backloggd search and you click the right "
                     "result. With it, each game opens its exact Backloggd page. You can skip "
                     "this and turn it on later in Settings.")
        self.para("You need a free Twitch account with two-factor authentication turned on.",
                  muted=True)
        self.numbered(1, "Open Twitch's developer page and sign in.")
        self.link_button("Open Twitch developer page", TWITCH_CREATE_URL)
        self.numbered(2, "Name: type something unique, like “Backloggd Checklist” and your name.")
        self.numbered(3, "OAuth Redirect URLs: paste this, then click “Add”:")
        self.copy_field("http://localhost")
        self.numbered(4, "Category: “Application Integration”. Client Type: “Confidential”. "
                         "Then click “Create”.")
        self.numbered(5, "Click “Manage” next to your new app. Copy the Client ID and paste it here:")
        self.input_field("igdb_client_id")
        self.numbered(6, "Click “New Secret”, copy it and paste it here:")
        self.input_field("igdb_client_secret", secret=True)
        self.status_line()
        return self.igdb_button_text()

    def igdb_button_text(self):
        filled = any(self.vars[k].get().strip() for k in ("igdb_client_id", "igdb_client_secret"))
        return "Check and continue" if filled else "Skip"

    def update_igdb_button(self):
        if self.steps[self.index] == self.step_igdb and not self.busy:
            self.next_btn.configure(text=self.igdb_button_text())

    def step_done(self):
        self.heading("All set!", "Your settings are saved and encrypted on this computer.")
        if not self.has_igdb():
            self.para("Exact links are off, so games will open a Backloggd search. You can turn "
                      "them on any time from Settings.", muted=True)
        self.para("Next, the app reads your Steam library. Then click “Add to Backloggd” on any "
                  "game to open it on Backloggd.")
        return "Sync my library"

    # ---- navigation

    def show(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.status = None
        self.next_btn.configure(text=self.steps[self.index]())
        self.back_btn.configure(state="normal" if 0 < self.index < len(self.steps) - 1 else "disabled")
        inner = self.steps[1:-1]
        step = self.steps[self.index]
        self.step_label.configure(
            text=f"Step {inner.index(step) + 1} of {len(inner)}" if step in inner else "")

    def go(self, index):
        self.index = index
        self.show()

    def back(self):
        if not self.busy and self.index > 0:
            self.go(self.index - 1)

    def has_igdb(self):
        return all(self.vars[k].get().strip() for k in ("igdb_client_id", "igdb_client_secret"))

    def next(self):
        if self.busy:
            return
        step = self.steps[self.index]
        if step == self.step_steam_key:
            try:
                core.check_steam_key_format(self.vars["steam_api_key"].get())
            except core.SyncError as e:
                self.set_status(str(e), "Error.TLabel")
                return
            self.go(self.index + 1)
        elif step == self.step_steam_profile:
            self.run_check(lambda: core.check_steam(self.vars["steam_api_key"].get(),
                                                    self.vars["steam_id"].get()),
                           lambda r: f"✓ Found {r[1]} games in your Steam library.")
        elif step == self.step_igdb:
            if not any(self.vars[k].get().strip() for k in ("igdb_client_id", "igdb_client_secret")):
                self.go(self.index + 1)
                self.save()
                return
            self.run_check(lambda: core.check_igdb(self.vars["igdb_client_id"].get(),
                                                   self.vars["igdb_client_secret"].get()),
                           lambda r: "✓ Twitch accepted your keys. Exact links are on.",
                           then=self.save)
        elif step == self.step_done:
            self.sync_now = True
            self.destroy()
        else:
            self.go(self.index + 1)

    def save(self):
        cfg = {k: v.get().strip() for k, v in self.vars.items()}
        if not self.has_igdb():
            cfg["igdb_client_id"] = cfg["igdb_client_secret"] = ""
        core.save_config(cfg)
        self.result = cfg

    # ---- background checks (network calls must not freeze the window)

    def run_check(self, fn, ok_text, then=None):
        self.busy = True
        self.next_btn.configure(state="disabled")
        self.back_btn.configure(state="disabled")
        self.set_status("Checking…", "Muted.TLabel")

        def work():
            try:
                self.events.put(("ok", fn()))
            except core.SyncError as e:
                self.events.put(("error", str(e)))
            except Exception as e:
                self.events.put(("error", f"Something went wrong ({type(e).__name__}). Try again."))

        threading.Thread(target=work, daemon=True).start()
        self.after(100, lambda: self.poll_check(ok_text, then))

    def poll_check(self, ok_text, then):
        if not self.winfo_exists():
            return
        try:
            kind, payload = self.events.get_nowait()
        except queue.Empty:
            self.after(100, lambda: self.poll_check(ok_text, then))
            return
        self.busy = False
        self.next_btn.configure(state="normal")
        self.back_btn.configure(state="normal")
        if kind == "error":
            self.set_status(payload, "Error.TLabel")
            return
        self.set_status(ok_text(payload), "Ok.TLabel")

        def advance():
            if self.winfo_exists():
                if then:
                    then()
                self.go(self.index + 1)

        self.after(900, advance)


class HelpDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("How to use")
        self.transient(master)
        self.resizable(False, False)
        self.configure(bg=master.palette["bg"])
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=HELP_TEXT, justify="left").pack(anchor="w")
        ttk.Button(body, text="Close", command=self.destroy).pack(anchor="e", pady=(14, 0))
        self.bind("<Return>", lambda e: self.destroy())
        self.bind("<Escape>", lambda e: self.destroy())
        show_modal(self, master)


# ---------------------------------------------------------------- game details

class GameDetail(tk.Toplevel):
    """A game's banner, actions and Steam achievements."""

    def __init__(self, app, game):
        super().__init__(app)
        self.app, self.game = app, game
        S = app.scale
        self.S = S
        self.title(app.name_of(game))
        self.geometry(f"{round(660 * S)}x{round(760 * S)}")
        self.minsize(round(520 * S), round(480 * S))
        self.icon_labels = []
        self.blank = None
        self.protocol("WM_DELETE_WINDOW", self.close)

        outer = ttk.Frame(self, padding=round(18 * S))
        outer.pack(fill="both", expand=True)

        self.banner_size = (round(460 * S), round(215 * S))
        self.banner = tk.Canvas(outer, width=self.banner_size[0], height=self.banner_size[1],
                                highlightthickness=0, bd=0)
        self.banner.pack(anchor="w")
        ttk.Label(outer, text=app.name_of(game), style="Title.TLabel",
                  wraplength=round(600 * S)).pack(anchor="w", pady=(12, 2))
        ttk.Label(outer, style="Muted.TLabel", text=(
            f"Playtime: {app.fmt_playtime(game['playtime'])}   ·   "
            f"Last played: {app.fmt_last(game)}   ·   {app.link_label(game)}")).pack(anchor="w")

        actions = ttk.Frame(outer)
        actions.pack(anchor="w", pady=(12, 12))
        self.add_btn = ttk.Button(actions, style="Accent.TButton",
                                  command=lambda: app.open_backloggd(game))
        self.add_btn.pack(side="left")
        self.mark_btn = ttk.Button(actions, command=self.toggle_added)
        self.mark_btn.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Search on Backloggd ↗",
                   command=lambda: app.search_backloggd(game)).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Steam store ↗",
                   command=lambda: app.open_store(game)).pack(side="left", padx=(8, 0))
        self.update_buttons()

        ttk.Separator(outer).pack(fill="x", pady=(0, 12))
        head = ttk.Frame(outer)
        head.pack(fill="x")
        ttk.Label(head, text="Achievements", style="Heading.TLabel").pack(side="left")
        self.refresh_btn = ttk.Button(head, text="⟳ Refresh", command=lambda: self.load(force=True))
        self.refresh_btn.pack(side="right")
        self.summary = ttk.Label(outer, text="", style="Muted.TLabel", wraplength=round(600 * S),
                                 justify="left")
        self.summary.pack(anchor="w", pady=(6, 4))
        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.list = ScrollFrame(outer, app.palette["surface"])
        self.list.pack(fill="both", expand=True, pady=(6, 0))

        self.retheme()
        self.draw_banner()
        self.load()
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_width()) // 2
        y = app.winfo_rooty() + 30
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.focus_force()

    def close(self):
        self.app.details.pop(str(self.game["appid"]), None)
        self.destroy()

    def retheme(self):
        p = self.app.palette
        self.configure(bg=p["bg"])
        self.banner.configure(bg=p["bg"])
        self.list.canvas.configure(bg=p["surface"])
        for lbl in self.icon_labels:
            lbl.configure(bg=p["surface"])
        theme.set_titlebar(self, self.app.is_dark)
        self.draw_banner()

    def update_buttons(self):
        added = self.app.is_added(self.game)
        self.add_btn.configure(text="Open on Backloggd ↗" if added else "Add to Backloggd ↗")
        self.mark_btn.configure(text="✓ Marked as added" if added else "Mark as added")

    def toggle_added(self):
        self.app.toggle_added(self.game)
        self.update_buttons()

    def draw_banner(self):
        p = self.app.palette
        w, h = self.banner_size
        g = self.game
        img = self.app.images.get(("banner", g["appid"], self.banner_size),
                                  lambda: core.steam_art(g["appid"], "header"),
                                  self.banner_size, "cover", self.draw_banner_if_open)
        self.banner.delete("all")
        if img:
            self.banner.create_image(0, 0, image=img, anchor="nw")
        else:
            self.banner.create_rectangle(0, 0, w, h, fill=p["placeholder"], outline="")
            self.banner.create_text(w / 2, h / 2, text=self.app.name_of(g), fill=p["muted"],
                                    font=self.app.fonts["heading"], width=w - 40)

    def draw_banner_if_open(self):
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
            self.summary.configure(text="Sync your Steam library first to see achievements.",
                                   style="Muted.TLabel")
            return
        self.summary.configure(text="Loading achievements from Steam…", style="Muted.TLabel")
        self.refresh_btn.configure(state="disabled")
        cfg = dict(self.app.cfg)
        self.app.jobs.submit(lambda: core.fetch_achievements(cfg, steam_id, appid), self.loaded)

    def loaded(self, result, error):
        if not self.winfo_exists():
            return
        self.refresh_btn.configure(state="normal")
        if error is not None:
            msg = str(error) if isinstance(error, core.SyncError) else \
                f"Couldn't load achievements ({type(error).__name__}). Try Refresh."
            self.summary.configure(text=msg, style="Error.TLabel")
            return
        self.show_achievements(result)

    def show_achievements(self, data):
        for child in self.list.inner.winfo_children():
            child.destroy()
        self.icon_labels = []
        items = data.get("achievements", [])
        if not items:
            self.progress.pack_forget()
            self.summary.configure(text="This game has no Steam achievements.", style="Muted.TLabel")
            return
        done = sum(1 for a in items if a["achieved"])
        pct = round(100 * done / len(items))
        when = fmt_date(data.get("fetched_at", 0))
        self.summary.configure(style="TLabel",
                               text=f"{done} of {len(items)} unlocked ({pct}%)   ·   updated {when}")
        self.progress.configure(value=pct)
        self.progress.pack(fill="x", after=self.summary)
        for a in items:
            self.add_row(a)

    def add_row(self, a):
        S, p = self.S, self.app.palette
        row = ttk.Frame(self.list.inner, style="Card.TFrame", padding=(10, 8))
        row.pack(fill="x")
        size = (round(44 * S), round(44 * S))
        if self.blank is None:
            self.blank = tk.PhotoImage(width=size[0], height=size[1])
        icon = tk.Label(row, bg=p["surface"], image=self.blank, bd=0)
        icon.pack(side="left", anchor="n")
        self.icon_labels.append(icon)
        url = a["icon"] if a["achieved"] else (a["icon_locked"] or a["icon"])
        if url:
            key = ("ach", url, size)

            def ready(lbl=icon, k=key):
                if lbl.winfo_exists() and k in self.app.images.cache:
                    lbl.configure(image=self.app.images.cache[k])

            img = self.app.images.get(key, lambda u=url: core.url_image(u), size, "contain", ready)
            if img:
                icon.configure(image=img)

        right = ttk.Frame(row, style="Card.TFrame")
        right.pack(side="right", anchor="n", padx=(10, 0))
        if a["achieved"]:
            ttk.Label(right, text=f"Unlocked {fmt_date(a['unlocked_at'])}", style="CardBold.TLabel",
                      foreground=p["ok"]).pack(anchor="e")
        else:
            ttk.Label(right, text="Locked", style="CardMuted.TLabel").pack(anchor="e")
        if a.get("percent") is not None:
            ttk.Label(right, text=f"{a['percent']:.1f}% of players", style="CardMuted.TLabel"
                      ).pack(anchor="e")

        text = ttk.Frame(row, style="Card.TFrame")
        text.pack(side="left", fill="x", expand=True, padx=(12, 0))
        ttk.Label(text, text=a["name"], style="CardBold.TLabel",
                  foreground=p["text"] if a["achieved"] else p["muted"]).pack(anchor="w")
        if a.get("description"):
            ttk.Label(text, text=a["description"], style="CardMuted.TLabel",
                      wraplength=round(330 * S), justify="left").pack(anchor="w")
        ttk.Separator(self.list.inner).pack(fill="x")


# ---------------------------------------------------------------- main window

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
        self.geometry(f"{round(1100 * self.scale)}x{round(740 * self.scale)}")
        self.minsize(round(760 * self.scale), round(480 * self.scale))

        self.cfg = core.load_config()
        self.library = core.load_library()
        self.done = core.load_done()
        self.games = {str(g["appid"]): g for g in self.library["games"]}
        self.ui = core.load_ui()
        self.collapsed = set(self.ui.get("collapsed", []))
        self.view_mode = self.ui.get("view", "grid")
        self.theme_mode = self.ui.get("theme", "system")
        self.sort_key = self.ui.get("sort", "name")
        self.sort_desc = self.ui.get("sort_desc", False)
        self.details = {}
        self.events = queue.Queue()
        self.syncing = False

        self.fonts = theme.fonts(self)
        self.jobs = Jobs(self)
        self.images = ImageLoader(self.jobs)
        self.tooltip = Tooltip(self)
        self.is_dark = theme.resolve(self.theme_mode) == "dark"
        self.palette = theme.PALETTES["dark" if self.is_dark else "light"]
        theme.apply(self, self.palette, self.fonts)

        self._build_toolbar()
        self._build_view()
        self._build_footer()
        self.menu = tk.Menu(self, tearoff=False)
        self.apply_theme()
        self.after(150, lambda: theme.set_titlebar(self, self.is_dark))

        if not core.config_complete(self.cfg):
            self.after(300, lambda: self.open_settings(start=0))

    # ---- layout

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(14, 12, 14, 6))
        bar.pack(fill="x")
        self.sync_btn = ttk.Button(bar, text="⟳  Sync Steam library", style="Accent.TButton",
                                   command=self.start_sync)
        self.sync_btn.pack(side="left")
        ttk.Button(bar, text="Settings", command=self.open_settings).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="How to use", command=lambda: HelpDialog(self)).pack(side="left", padx=(8, 0))

        self.theme_btn = ttk.Menubutton(bar, text="Theme")
        self.theme_menu = tk.Menu(self.theme_btn, tearoff=False)
        self.theme_var = tk.StringVar(value=self.theme_mode)
        for value, label in (("system", "Same as Windows"), ("light", "Light"), ("dark", "Dark")):
            self.theme_menu.add_radiobutton(label=label, value=value, variable=self.theme_var,
                                            command=lambda v=value: self.set_theme(v))
        self.theme_btn.configure(menu=self.theme_menu)
        self.theme_btn.pack(side="right")

        self.view_btns = {}
        for mode, label in (("list", "☰  List"), ("grid", "▦  Grid")):
            b = ttk.Button(bar, text=label, command=lambda m=mode: self.set_view(m))
            b.pack(side="right", padx=(0, 8 if mode == "grid" else 2))
            self.view_btns[mode] = b
        ttk.Label(bar, text="View", style="Muted.TLabel").pack(side="right", padx=(0, 6))

        filters = ttk.Frame(self, padding=(14, 2, 14, 8))
        filters.pack(fill="x")
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *a: self.refresh())
        search = ttk.Entry(filters, textvariable=self.query, width=26)
        search.pack(side="left")
        self._placeholder(search, "Search games…")
        self.bind("<Control-f>", lambda e: search.focus_set())

        ttk.Label(filters, text="Sort", style="Muted.TLabel").pack(side="left", padx=(16, 6))
        self.sort_btns = {}
        for key, label in self.SORTS:
            b = ttk.Button(filters, command=lambda k=key: self.set_sort(k))
            b.pack(side="left", padx=(0, 2))
            self.sort_btns[key] = b

        self.hide_done = tk.BooleanVar()
        ttk.Checkbutton(filters, text="Hide added", variable=self.hide_done,
                        command=self.refresh).pack(side="left", padx=(16, 10))
        self.only_unmatched = tk.BooleanVar()
        ttk.Checkbutton(filters, text="Only search links", variable=self.only_unmatched,
                        command=self.refresh).pack(side="left")

    def _placeholder(self, entry, text):
        """Grey hint text inside the search box while it's empty."""
        def show(_=None):
            if not self.query.get():
                entry.configure(foreground=self.palette["muted"])
                entry.insert(0, text)
                entry.placeholder = True

        def hide(_=None):
            if getattr(entry, "placeholder", False):
                entry.placeholder = False
                entry.delete(0, "end")
                entry.configure(foreground=self.palette["text"])

        entry.placeholder = False
        self._search_hint = text
        self.search_entry = entry
        entry.bind("<FocusIn>", hide)
        entry.bind("<FocusOut>", show)
        self.after(50, show)

    def _build_view(self):
        area = ttk.Frame(self, padding=(14, 0, 14, 0))
        area.pack(fill="both", expand=True)
        self.view = GameView(area, self)
        self.header = ListHeader(area, self, self.view)
        self.scrollbar = ttk.Scrollbar(area, orient="vertical", command=self.view.yview)
        self.view.scrollbar = self.scrollbar
        self.view.configure(yscrollcommand=self.view.on_scroll)
        self.scrollbar.pack(side="right", fill="y")
        self.view.pack(side="bottom", fill="both", expand=True)

    def _build_footer(self):
        status = ttk.Frame(self, padding=(14, 8, 14, 10))
        status.pack(fill="x")
        self.counter = ttk.Label(status, text="")
        self.counter.pack(side="right")
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=120)
        self.status = ttk.Label(status, text="", style="Muted.TLabel")
        self.status.pack(side="left")

    # ---- small helpers used by the view

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

    def tip_text(self, g):
        if not g["playtime"]:
            return "Not played yet"
        return f"Playtime: {fmt_playtime(g['playtime'])}\nLast played: {fmt_date(g['last'])}"

    def sort_arrow(self, key):
        if key != self.sort_key:
            return ""
        return "  ▼" if self.sort_desc else "  ▲"

    def empty_text(self):
        if not self.games:
            return "No games yet.\n\nClick “Sync Steam library” to load your games."
        return "No games match the current filters."

    # ---- state changes

    def save_ui(self):
        self.ui.update({"collapsed": sorted(self.collapsed), "view": self.view_mode,
                        "theme": self.theme_mode, "sort": self.sort_key, "sort_desc": self.sort_desc})
        core.save_ui(self.ui)

    def set_sort(self, key):
        if key == self.sort_key:
            self.sort_desc = not self.sort_desc
        else:
            # Most played / most recent first feels natural; names start at A
            self.sort_key, self.sort_desc = key, key != "name"
        self.save_ui()
        self.refresh()

    def set_view(self, mode):
        self.view_mode = mode
        self.save_ui()
        self.view.yview_moveto(0)
        self.refresh()

    def set_theme(self, mode):
        self.theme_mode = mode
        self.save_ui()
        self.apply_theme()

    def apply_theme(self):
        self.is_dark = theme.resolve(self.theme_mode) == "dark"
        self.palette = theme.PALETTES["dark" if self.is_dark else "light"]
        theme.apply(self, self.palette, self.fonts)
        p = self.palette
        self.configure(bg=p["bg"])
        for m in (self.menu, self.theme_menu):
            m.configure(bg=p["surface"], fg=p["text"], activebackground=p["accent"],
                        activeforeground=p["accent_text"], selectcolor=p["accent"])
        self.theme_btn.configure(text={"system": "Theme: Auto", "light": "Theme: Light",
                                       "dark": "Theme: Dark"}[self.theme_mode])
        self.search_entry.configure(foreground=p["muted"] if self.search_entry.placeholder else p["text"])
        theme.set_titlebar(self, self.is_dark)
        for d in list(self.details.values()):
            d.retheme()
        self.refresh()

    def toggle_group(self, gid):
        self.collapsed.symmetric_difference_update({gid})
        self.save_ui()
        self.refresh()

    def toggle_added(self, g):
        self.done.symmetric_difference_update({str(g["appid"])})
        core.save_done(self.done)
        self.refresh()
        d = self.details.get(str(g["appid"]))
        if d:
            d.update_buttons()

    def open_backloggd(self, g):
        webbrowser.open(core.backloggd_url(g))

    def search_backloggd(self, g):
        webbrowser.open(core.backloggd_search_url(g))

    def open_store(self, g):
        webbrowser.open(f"https://store.steampowered.com/app/{g['appid']}/")

    def open_details(self, g):
        key = str(g["appid"])
        if key in self.details and self.details[key].winfo_exists():
            self.details[key].lift()
            self.details[key].focus_force()
            return
        self.details[key] = GameDetail(self, g)

    def show_menu(self, g, x, y):
        m = self.menu
        m.delete(0, "end")
        m.add_command(label="Details and achievements", command=lambda: self.open_details(g))
        m.add_command(label="Open on Backloggd" if self.is_added(g) else "Add to Backloggd",
                      command=lambda: self.open_backloggd(g))
        m.add_command(label="Search on Backloggd (if the page doesn't open)",
                      command=lambda: self.search_backloggd(g))
        m.add_separator()
        m.add_command(label="Mark as not added" if self.is_added(g) else "Mark as added",
                      command=lambda: self.toggle_added(g))
        m.add_command(label="Open in Steam store", command=lambda: self.open_store(g))
        m.tk_popup(x, y)

    # ---- list

    def query_text(self):
        q = self.query.get()
        return "" if q == self._search_hint else q.strip().lower()

    def visible_games(self):
        q = self.query_text()
        out = []
        for appid, g in self.games.items():
            if q and q not in self.name_of(g).lower() and q not in g["steam_name"].lower():
                continue
            if self.hide_done.get() and appid in self.done:
                continue
            if self.only_unmatched.get() and g["slug"]:
                continue
            out.append(g)
        return out

    def sorted_games(self, games, played):
        games.sort(key=lambda g: self.name_of(g).lower(), reverse=self.sort_key == "name" and self.sort_desc)
        if self.sort_key == "playtime" and played:
            games.sort(key=lambda g: g["playtime"], reverse=self.sort_desc)
        elif self.sort_key == "last":
            # For unplayed games this orders by purchase date: newest purchases first
            games.sort(key=lambda g: g["last"], reverse=self.sort_desc)
        return games

    def refresh(self):
        for key, label in self.SORTS:
            self.sort_btns[key].configure(text=label + self.sort_arrow(key),
                                          style="SegOn.TButton" if key == self.sort_key else "Seg.TButton")
        for mode, b in self.view_btns.items():
            b.configure(style="SegOn.TButton" if mode == self.view_mode else "Seg.TButton")
        if self.view_mode == "list":
            self.header.pack(side="top", fill="x", before=self.view)
            self.header.render()
        else:
            self.header.pack_forget()

        games = self.visible_games()
        groups = []
        for gid, title, belongs in self.GROUPS:
            members = self.sorted_games([g for g in games if belongs(g)], gid == "grp:played")
            if members:
                groups.append((gid, title, members, gid not in self.collapsed))
        self.view.set_data(groups, self.view_mode)

        total = len(self.games)
        self.counter.configure(text=f"{len(self.done & self.games.keys())} of {total} added" if total else "")
        if not self.syncing:
            self.status.configure(text=self.last_sync_text())

    def last_sync_text(self):
        ts = self.library.get("synced_at")
        if not ts:
            return "Not synced yet."
        when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        if not core.igdb_enabled(self.cfg):
            return f"Last synced {when} · Exact Backloggd links are off (optional, see Settings)"
        matched = sum(1 for g in self.games.values() if g["slug"])
        return f"Last synced {when} · {matched} of {len(self.games)} games have an exact Backloggd link"

    def open_settings(self, start=1):
        wizard = SetupWizard(self, self.cfg, start=start)
        self.wait_window(wizard)
        if wizard.result:
            self.cfg = wizard.result
            self.refresh()
        if wizard.sync_now:
            self.start_sync()

    # ---- sync (runs in a background thread; results come back through a queue)

    def start_sync(self):
        if self.syncing:
            return
        if not core.config_complete(self.cfg):
            self.open_settings(start=0)
            return
        self.syncing = True
        self.sync_btn.configure(state="disabled")
        self.progress.pack(side="right", padx=(0, 12))
        self.progress.start(12)
        cfg = dict(self.cfg)

        def work():
            try:
                lib = core.sync_library(cfg, progress=lambda m: self.events.put(("status", m)))
                self.events.put(("done", lib))
            except core.SyncError as e:
                self.events.put(("error", str(e)))
            except Exception as e:  # unexpected: show the type only, never request details
                self.events.put(("error", f"Something went wrong ({type(e).__name__}). Try again."))

        threading.Thread(target=work, daemon=True).start()
        self.after(100, self.poll_sync)

    def poll_sync(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "status":
                    self.status.configure(text=payload)
                    continue
                self.syncing = False
                self.progress.stop()
                self.progress.pack_forget()
                self.sync_btn.configure(state="normal")
                if kind == "done":
                    before = len(self.games)
                    self.library = payload
                    self.games = {str(g["appid"]): g for g in payload["games"]}
                    self.refresh()
                    new = len(self.games) - before
                    if before and new > 0:
                        self.status.configure(text=f"{new} new games added. " + self.last_sync_text())
                else:
                    self.refresh()
                    messagebox.showerror("Sync failed", payload, parent=self)
                return
        except queue.Empty:
            self.after(100, self.poll_sync)


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
