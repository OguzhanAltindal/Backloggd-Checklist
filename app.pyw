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
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import checklist_core as core

STEAM_KEY_URL = "https://steamcommunity.com/dev/apikey"
STEAM_PROFILE_URL = "https://steamcommunity.com/my/profile"
STEAM_PRIVACY_URL = "https://steamcommunity.com/my/edit/settings"
TWITCH_CREATE_URL = "https://dev.twitch.tv/console/apps/create"

MUTED = "#5f6670"
OK_COLOR = "#1d7a34"
ERROR_COLOR = "#b3261e"

HELP_TEXT = """\
1. Click “Settings” to run the setup (about 2 minutes, done once).
2. Click “Sync Steam library”. Your games appear in two groups,
   “Played” and “Not played yet”. Click the small box next to a group
   to close or open it. Click a column title to sort by it.
3. Sign in to backloggd.com in your browser as usual.
4. Double-click a game (or select it and click “Open on Backloggd”).
   Backloggd opens in your browser: log the game there yourself.
5. Press Space (or click the ✓ column) to mark the game as added.
   Tick “Hide added” to keep the list short.
6. Games with a “search” link open a Backloggd search: click the
   right result. Exact links can be turned on in Settings (optional).
   If a game's page shows “Page not found”, right-click the game and
   choose “Search on Backloggd”.
7. Bought new games? Click “Sync Steam library” again. Your marks are kept.

Your safety:
• The app never asks for a password and never logs in to any account.
• It only talks to the official Steam Web API and the official IGDB API.
• It never sends anything to Backloggd: you add every game yourself.
• Your keys are encrypted with your Windows account and stored only on this computer."""


def fmt_playtime(m):
    if not m:
        return "never played"
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
    dialog.grab_set()
    dialog.wait_visibility()
    dialog.focus_force()


# ---------------------------------------------------------------- setup wizard

class SetupWizard(tk.Toplevel):
    """Step-by-step setup written for people who have never used an API."""

    WIDTH = 600
    WRAP = 540

    def __init__(self, master, cfg, start=0):
        super().__init__(master)
        self.title("Setup")
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        self.sync_now = False
        self.events = queue.Queue()
        self.busy = False
        cfg = cfg or {}
        self.vars = {k: tk.StringVar(value=cfg.get(k, "")) for k in core.CONFIG_KEYS}
        for key in ("igdb_client_id", "igdb_client_secret"):
            self.vars[key].trace_add("write", lambda *a: self.update_igdb_button())

        self.steps = [self.step_welcome, self.step_steam_key, self.step_steam_profile,
                      self.step_igdb, self.step_done]
        self.index = start

        self.body = ttk.Frame(self, padding=(24, 20, 24, 8), width=self.WIDTH)
        self.body.pack(fill="both", expand=True)
        ttk.Separator(self).pack(fill="x")
        footer = ttk.Frame(self, padding=(24, 12))
        footer.pack(fill="x")
        self.step_label = ttk.Label(footer, foreground=MUTED)
        self.step_label.pack(side="left")
        self.next_btn = ttk.Button(footer, command=self.next, default="active")
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(footer, text="Back", command=self.back)
        self.back_btn.pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda e: self.destroy())
        self.show()
        show_modal(self, master)

    # ---- page building helpers

    def heading(self, text, sub=None):
        ttk.Label(self.body, text=text, font=("Segoe UI", 14, "bold")).pack(anchor="w")
        if sub:
            ttk.Label(self.body, text=sub, foreground=MUTED, wraplength=self.WRAP,
                      justify="left").pack(anchor="w", pady=(2, 0))
        ttk.Frame(self.body, height=14).pack()

    def para(self, text, muted=False, pady=(0, 8)):
        ttk.Label(self.body, text=text, wraplength=self.WRAP, justify="left",
                  foreground=MUTED if muted else "").pack(anchor="w", pady=pady)

    def numbered(self, n, text):
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(6, 4))
        ttk.Label(row, text=f"{n}.", width=3, font=("Segoe UI", 10, "bold")).pack(side="left", anchor="n")
        ttk.Label(row, text=text, wraplength=self.WRAP - 30, justify="left").pack(side="left", anchor="w")

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
        box = ttk.Entry(frame, width=24, font=("Consolas", 11))
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
        self.status = ttk.Label(self.body, text="", wraplength=self.WRAP, justify="left")
        self.status.pack(anchor="w", pady=(10, 0))

    def set_status(self, text, color=""):
        self.status.configure(text=text, foreground=color)

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
        self.para("Next, the app reads your Steam library. Then double-click any game to open "
                  "it on Backloggd.")
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
                self.set_status(str(e), ERROR_COLOR)
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
        self.set_status("Checking…", MUTED)

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
            self.set_status(payload, ERROR_COLOR)
            return
        self.set_status(ok_text(payload), OK_COLOR)

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
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=HELP_TEXT, justify="left").pack(anchor="w")
        ttk.Button(body, text="Close", command=self.destroy).pack(anchor="e", pady=(14, 0))
        self.bind("<Return>", lambda e: self.destroy())
        self.bind("<Escape>", lambda e: self.destroy())
        show_modal(self, master)


# ---------------------------------------------------------------- main window

class App(tk.Tk):
    # The game name lives in the tree column (#0) so it can sit under a collapsible group
    COLUMNS = (("done", "Added", 60, "center"),
               ("playtime", "Playtime", 110, "e"), ("last", "Last played", 110, "center"),
               ("match", "Backloggd link", 120, "center"))
    # Games with no playtime were never played (a recent date there only means a recent purchase)
    GROUPS = (("grp:played", "Played", lambda g: g["playtime"] > 0),
              ("grp:unplayed", "Not played yet", lambda g: g["playtime"] == 0))

    def __init__(self):
        super().__init__()
        self.title("Backloggd Checklist")
        # Next to the script, or inside the bundle when packaged with PyInstaller
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "icon.ico"
        if icon.exists():
            self.iconbitmap(default=str(icon))
        self.geometry("880x620")
        self.minsize(640, 400)

        self.cfg = core.load_config()
        self.library = core.load_library()
        self.done = core.load_done()
        self.games = {str(g["appid"]): g for g in self.library["games"]}
        self.ui = core.load_ui()
        self.collapsed = set(self.ui.get("collapsed", []))
        self.events = queue.Queue()
        self.syncing = False

        style = ttk.Style(self)
        linespace = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        style.configure("Treeview", rowheight=linespace + 10)

        self._build_toolbar()
        self._build_list(style)
        self._build_footer()
        self.refresh()

        if not core.config_complete(self.cfg):
            self.after(200, lambda: self.open_settings(start=0))

    # ---- layout

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(12, 12, 12, 6))
        bar.pack(fill="x")
        self.sync_btn = ttk.Button(bar, text="⟳  Sync Steam library", command=self.start_sync)
        self.sync_btn.pack(side="left")
        ttk.Button(bar, text="Settings", command=self.open_settings).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="How to use", command=lambda: HelpDialog(self)).pack(side="left", padx=(8, 0))

        filters = ttk.Frame(self, padding=(12, 0, 12, 8))
        filters.pack(fill="x")
        ttk.Label(filters, text="Search").pack(side="left")
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *a: self.refresh())
        search = ttk.Entry(filters, textvariable=self.query, width=28)
        search.pack(side="left", padx=(6, 14))
        self.bind("<Control-f>", lambda e: search.focus_set())

        ttk.Label(filters, text="Sort").pack(side="left")
        self.sort = tk.StringVar(value="Name")
        sort_box = ttk.Combobox(filters, textvariable=self.sort, state="readonly", width=12,
                                values=("Name", "Playtime", "Last played"))
        sort_box.pack(side="left", padx=(6, 14))
        sort_box.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        self.hide_done = tk.BooleanVar()
        ttk.Checkbutton(filters, text="Hide added", variable=self.hide_done,
                        command=self.refresh).pack(side="left", padx=(0, 10))
        self.only_unmatched = tk.BooleanVar()
        ttk.Checkbutton(filters, text="Only search links", variable=self.only_unmatched,
                        command=self.refresh).pack(side="left")

    def _build_list(self, style):
        frame = ttk.Frame(self, padding=(12, 0))
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in self.COLUMNS],
                                 show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Game", anchor="w", command=lambda: self.set_sort("Name"))
        self.tree.column("#0", width=380, anchor="w", stretch=True)
        sort_by_heading = {"playtime": "Playtime", "last": "Last played"}
        for key, title, width, anchor in self.COLUMNS:
            self.tree.heading(key, text=title, anchor=anchor)
            if key in sort_by_heading:
                self.tree.heading(key, command=lambda s=sort_by_heading[key]: self.set_sort(s))
            self.tree.column(key, width=width, anchor=anchor, stretch=False)
        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")
        self.tree.tag_configure("group", font=bold)
        self.tree.tag_configure("done", foreground="#9a9a9a")
        self.tree.tag_configure("unmatched", foreground="#a86400")
        self.tree.bind("<<TreeviewOpen>>", lambda e: self.remember_group(open_=True))
        self.tree.bind("<<TreeviewClose>>", lambda e: self.remember_group(open_=False))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-1>", self.on_click, add="+")
        self.tree.bind("<Return>", lambda e: self.open_selected())
        self.tree.bind("<space>", lambda e: self.toggle_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_buttons())
        self.tree.bind("<Button-3>", self.on_right_click)

        self.menu = tk.Menu(self, tearoff=False)
        self.menu.add_command(label="Open on Backloggd", command=self.open_selected)
        self.menu.add_command(label="Search on Backloggd (if the page doesn't open)",
                              command=self.search_selected)
        self.menu.add_command(label="Mark as added / not added", command=self.toggle_selected)
        self.menu.add_command(label="Open in Steam store", command=self.open_store)

        bg = style.lookup("Treeview", "fieldbackground") or "white"
        self.empty = tk.Label(frame, text="", fg="#777", bg=bg, justify="center")

    def _build_footer(self):
        actions = ttk.Frame(self, padding=(12, 8, 12, 4))
        actions.pack(fill="x")
        self.open_btn = ttk.Button(actions, text="Open on Backloggd", command=self.open_selected)
        self.open_btn.pack(side="left")
        self.toggle_btn = ttk.Button(actions, text="Mark as added", command=self.toggle_selected)
        self.toggle_btn.pack(side="left", padx=(8, 0))
        self.counter = ttk.Label(actions, text="")
        self.counter.pack(side="right")

        status = ttk.Frame(self, padding=(12, 0, 12, 10))
        status.pack(fill="x")
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=120)
        self.status = ttk.Label(status, text="", foreground="#666")
        self.status.pack(side="left")

    # ---- list

    def visible_games(self):
        q = self.query.get().strip().lower()
        games = []
        for appid, g in self.games.items():
            name = g["igdb_name"] or g["steam_name"]
            if q and q not in name.lower() and q not in g["steam_name"].lower():
                continue
            if self.hide_done.get() and appid in self.done:
                continue
            if self.only_unmatched.get() and g["slug"]:
                continue
            games.append(g)
        sort = self.sort.get()
        games.sort(key=lambda g: (g["igdb_name"] or g["steam_name"]).lower())
        if sort == "Playtime":
            games.sort(key=lambda g: -g["playtime"])
        elif sort == "Last played":
            games.sort(key=lambda g: -g["last"])
        return games

    def set_sort(self, value):
        self.sort.set(value)
        self.refresh()

    def remember_group(self, open_):
        iid = self.tree.focus()
        if not iid.startswith("grp:"):
            return
        (self.collapsed.discard if open_ else self.collapsed.add)(iid)
        self.ui["collapsed"] = sorted(self.collapsed)
        core.save_ui(self.ui)

    def refresh(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        # Only highlight search links when exact links are on; otherwise every game is one
        highlight = core.igdb_enabled(self.cfg)
        games = self.visible_games()
        for gid, title, belongs in self.GROUPS:
            members = [g for g in games if belongs(g)]
            if not members:
                continue
            self.tree.insert("", "end", iid=gid, text=f"{title}  ({len(members)})",
                             open=gid not in self.collapsed, tags=("group",))
            for g in members:
                appid = str(g["appid"])
                is_done = appid in self.done
                if is_done:
                    tags = ("done",)
                elif not g["slug"] and highlight:
                    tags = ("unmatched",)
                else:
                    tags = ()
                self.tree.insert(gid, "end", iid=appid, tags=tags,
                                 text=g["igdb_name"] or g["steam_name"], values=(
                                     "✓" if is_done else "",
                                     fmt_playtime(g["playtime"]),
                                     # Unplayed games: Steam's date is the purchase, not a session
                                     fmt_date(g["last"]) if g["playtime"] else "—",
                                     "exact page" if g["slug"] else "search",
                                 ))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
            self.tree.see(selected[0])

        total = len(self.games)
        self.counter.configure(text=f"{len(self.done & self.games.keys())} / {total} added" if total else "")
        if not total:
            self.empty.configure(text="No games yet.\n\nClick “Sync Steam library” to load your games.")
            self.empty.place(relx=0.5, rely=0.4, anchor="center")
        elif not self.tree.get_children():
            self.empty.configure(text="No games match the current filters.")
            self.empty.place(relx=0.5, rely=0.4, anchor="center")
        else:
            self.empty.place_forget()
        if not self.syncing:
            self.status.configure(text=self.last_sync_text())
        self.update_buttons()

    def last_sync_text(self):
        ts = self.library.get("synced_at")
        if not ts:
            return "Not synced yet."
        when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        if not core.igdb_enabled(self.cfg):
            return f"Last synced {when} · Exact Backloggd links are off (optional, see Settings)"
        matched = sum(1 for g in self.games.values() if g["slug"])
        return f"Last synced {when} · {matched} of {len(self.games)} games have an exact Backloggd link"

    def update_buttons(self):
        g = self.selected_game()
        state = "normal" if g else "disabled"
        self.open_btn.configure(state=state,
                                text="Search on Backloggd" if g and not g["slug"] else "Open on Backloggd")
        self.toggle_btn.configure(state=state,
                                  text="Mark as not added" if g and str(g["appid"]) in self.done
                                  else "Mark as added")

    def selected_game(self):
        sel = self.tree.selection()
        return self.games.get(sel[0]) if sel else None

    # ---- actions

    def open_selected(self):
        g = self.selected_game()
        if g:
            webbrowser.open(core.backloggd_url(g))

    def search_selected(self):
        g = self.selected_game()
        if g:
            webbrowser.open(core.backloggd_search_url(g))

    def open_store(self):
        g = self.selected_game()
        if g:
            webbrowser.open(f"https://store.steampowered.com/app/{g['appid']}/")

    def toggle_selected(self):
        g = self.selected_game()
        if not g:
            return
        appid = str(g["appid"])
        self.done.symmetric_difference_update({appid})
        core.save_done(self.done)
        # Keep the cursor moving down the list when hiding added games
        nxt = self.tree.next(appid) or self.tree.prev(appid)
        self.refresh()
        target = appid if self.tree.exists(appid) else nxt
        if target and self.tree.exists(target):
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)

    def on_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        if row and self.tree.identify_column(event.x) == "#1":
            self.tree.selection_set(row)
            self.toggle_selected()
            return "break"

    def on_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) != "#1":
            self.open_selected()

    def on_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.menu.tk_popup(event.x_root, event.y_root)

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
        self.progress.pack(side="right")
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
