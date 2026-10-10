"""Light and dark themes: colors, ttk styles and the Windows title bar."""

import sys
from tkinter import font as tkfont
from tkinter import ttk

PALETTES = {
    "light": {
        "bg": "#f3f4f6", "surface": "#ffffff", "surface2": "#e9ecf0", "border": "#d6dae0",
        "text": "#1b1f24", "muted": "#5f6670", "accent": "#d93d63", "accent_hover": "#bf2f53",
        "accent_text": "#ffffff", "ok": "#1d7a34", "error": "#b3261e", "warn": "#9a5b00",
        "placeholder": "#d5d9df", "tip_bg": "#111418", "tip_text": "#ffffff", "link": "#1a62c4",
    },
    "dark": {
        "bg": "#14171c", "surface": "#1d2128", "surface2": "#272c35", "border": "#353c47",
        "text": "#e8eaee", "muted": "#9aa3b2", "accent": "#ff6b8b", "accent_hover": "#ff8ca5",
        "accent_text": "#1b0a10", "ok": "#62d083", "error": "#ff8a80", "warn": "#f3c56b",
        "placeholder": "#2b313b", "tip_bg": "#000000", "tip_text": "#ffffff", "link": "#7ab4ff",
    },
}


def system_prefers_dark():
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def resolve(mode):
    """'system' | 'light' | 'dark' -> 'light' | 'dark'"""
    if mode == "system":
        return "dark" if system_prefers_dark() else "light"
    return mode if mode in PALETTES else "light"


def set_titlebar(win, dark):
    """Ask Windows to draw this window's title bar dark or light."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, then old Windows 10)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        # Repaint the frame now instead of on the next focus change
        flags = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE | NOMOVE | NOZORDER | FRAMECHANGED
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
    except Exception:
        pass


def fonts(root):
    base = tkfont.nametofont("TkDefaultFont")
    size = base.cget("size")
    family = base.cget("family")
    return {
        "base": base,
        "bold": tkfont.Font(root, family=family, size=size, weight="bold"),
        "small": tkfont.Font(root, family=family, size=max(abs(size) - 1, 7) * (1 if size > 0 else -1)),
        "title": tkfont.Font(root, family=family, size=14 if size > 0 else -19, weight="bold"),
        "heading": tkfont.Font(root, family=family, size=11 if size > 0 else -15, weight="bold"),
        "mono": tkfont.Font(root, family="Consolas", size=11 if size > 0 else -15),
    }


def apply(root, p, f):
    """Configure every ttk style the app uses for palette `p`."""
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=p["bg"], foreground=p["text"], fieldbackground=p["surface"],
                bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"],
                troughcolor=p["surface2"], focuscolor=p["accent"], insertcolor=p["text"],
                selectbackground=p["accent"], selectforeground=p["accent_text"], font=f["base"])

    s.configure("TFrame", background=p["bg"])
    s.configure("Card.TFrame", background=p["surface"])
    s.configure("TLabel", background=p["bg"], foreground=p["text"])
    s.configure("Muted.TLabel", foreground=p["muted"])
    s.configure("Bold.TLabel", font=f["bold"])
    s.configure("Title.TLabel", font=f["title"])
    s.configure("Heading.TLabel", font=f["heading"])
    s.configure("Ok.TLabel", foreground=p["ok"])
    s.configure("Error.TLabel", foreground=p["error"])
    s.configure("Link.TLabel", foreground=p["link"])
    for name in ("Card", "CardMuted", "CardBold"):
        s.configure(f"{name}.TLabel", background=p["surface"],
                    foreground=p["muted"] if name == "CardMuted" else p["text"],
                    font=f["bold"] if name == "CardBold" else f["base"])

    s.configure("TButton", background=p["surface2"], foreground=p["text"], bordercolor=p["border"],
                lightcolor=p["surface2"], darkcolor=p["surface2"], padding=(10, 4), focusthickness=0)
    s.map("TButton",
          background=[("disabled", p["bg"]), ("pressed", p["border"]), ("active", p["border"])],
          foreground=[("disabled", p["muted"])],
          lightcolor=[("active", p["border"])], darkcolor=[("active", p["border"])])
    s.configure("Accent.TButton", background=p["accent"], foreground=p["accent_text"],
                bordercolor=p["accent"], lightcolor=p["accent"], darkcolor=p["accent"])
    s.map("Accent.TButton",
          background=[("pressed", p["accent_hover"]), ("active", p["accent_hover"])],
          lightcolor=[("active", p["accent_hover"])], darkcolor=[("active", p["accent_hover"])])
    # Segmented buttons (view switch, sort): the selected one is highlighted
    s.configure("Seg.TButton", padding=(9, 3))
    s.configure("SegOn.TButton", padding=(9, 3), background=p["surface"], bordercolor=p["accent"],
                foreground=p["accent"], lightcolor=p["surface"], darkcolor=p["surface"])
    s.map("SegOn.TButton", background=[("active", p["surface"])])

    s.configure("TEntry", fieldbackground=p["surface"], foreground=p["text"],
                bordercolor=p["border"], lightcolor=p["surface"], darkcolor=p["surface"], padding=4)
    s.map("TEntry", bordercolor=[("focus", p["accent"])],
          fieldbackground=[("readonly", p["surface2"])], lightcolor=[("focus", p["accent"])])
    s.configure("TCheckbutton", background=p["bg"], foreground=p["text"],
                indicatorbackground=p["surface"], indicatorforeground=p["accent"],
                upperbordercolor=p["border"], lowerbordercolor=p["border"])
    s.map("TCheckbutton", background=[("active", p["bg"])],
          indicatorbackground=[("pressed", p["surface2"]), ("selected", p["surface"])])
    s.configure("TMenubutton", background=p["surface2"], foreground=p["text"],
                bordercolor=p["border"], arrowcolor=p["text"], padding=(10, 4),
                lightcolor=p["surface2"], darkcolor=p["surface2"])
    s.map("TMenubutton", background=[("active", p["border"])])

    s.configure("Vertical.TScrollbar", background=p["surface2"], troughcolor=p["bg"],
                bordercolor=p["bg"], arrowcolor=p["muted"], lightcolor=p["surface2"],
                darkcolor=p["surface2"], gripcount=0)
    s.map("Vertical.TScrollbar", background=[("active", p["border"])])
    s.configure("Horizontal.TProgressbar", background=p["accent"], troughcolor=p["surface2"],
                bordercolor=p["border"], lightcolor=p["accent"], darkcolor=p["accent"])
    s.configure("TSeparator", background=p["border"])

    root.option_add("*Menu.background", p["surface"])
    root.option_add("*Menu.foreground", p["text"])
    root.option_add("*Menu.activeBackground", p["accent"])
    root.option_add("*Menu.activeForeground", p["accent_text"])
    root.option_add("*TCombobox*Listbox.background", p["surface"])
    root.option_add("*TCombobox*Listbox.foreground", p["text"])
