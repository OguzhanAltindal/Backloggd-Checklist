"""Design tokens (colors, type, spacing, icons) and ttk styles for light and dark mode."""

import sys
from tkinter import font as tkfont
from tkinter import ttk

# One primary (brand pink), neutral grays, one accent (green: "added" / "unlocked").
# Every color in the app comes from here.
PALETTES = {
    "light": {
        "bg": "#f6f6f8", "surface": "#ffffff", "raised": "#eef0f3",
        "border": "#e1e4e9", "border_strong": "#c4c9d1",
        "text": "#15171c", "muted": "#596170",
        "primary": "#c42d55", "primary_hover": "#a92447", "on_primary": "#ffffff",
        "primary_soft": "#fbe9ee", "primary_text": "#a3234a",
        "accent": "#1c7a43", "accent_soft": "#e4f4ea",
        "error": "#b42318", "error_soft": "#fdecea", "info_soft": "#eef1f6",
        "placeholder": "#e3e6eb", "shadow": "#000000", "focus": "#c42d55",
    },
    "dark": {
        "bg": "#111317", "surface": "#181b21", "raised": "#21252d",
        "border": "#2a2f38", "border_strong": "#3d4450",
        "text": "#eceef2", "muted": "#a1a9b6",
        "primary": "#ff7d9b", "primary_hover": "#ff98b0", "on_primary": "#2b0912",
        "primary_soft": "#38202a", "primary_text": "#ff9fb6",
        "accent": "#5ccf8b", "accent_soft": "#183326",
        "error": "#ff8a80", "error_soft": "#3a1f1e", "info_soft": "#1d2129",
        "placeholder": "#252a33", "shadow": "#000000", "focus": "#ff7d9b",
    },
}

# Primary color choices. Each keeps WCAG AA contrast in both modes: `on_primary` is the text
# on a filled button, `primary_text` is primary-colored text, `focus` is the keyboard focus ring.
ACCENT_NAMES = (("pink", "Pink"), ("green", "Green"), ("yellow", "Yellow"), ("blue", "Blue"),
                ("red", "Red"), ("magenta", "Magenta"))
ACCENTS = {
    "light": {
        "pink":    ("#c42d55", "#a92447", "#ffffff", "#fbe9ee", "#a3234a", "#c42d55"),
        "green":   ("#1b7a47", "#15633a", "#ffffff", "#e3f3ea", "#15633a", "#1b7a47"),
        "yellow":  ("#f0b400", "#d9a200", "#1f1700", "#fdf3d0", "#7a5600", "#7a5600"),
        "blue":    ("#2462c8", "#1d4fa3", "#ffffff", "#e6eefb", "#1d4fa3", "#2462c8"),
        "red":     ("#c42626", "#a51f1f", "#ffffff", "#fbe7e7", "#a51f1f", "#c42626"),
        "magenta": ("#ad268d", "#911f76", "#ffffff", "#f8e6f3", "#911f76", "#ad268d"),
    },
    "dark": {
        "pink":    ("#ff7d9b", "#ff98b0", "#2b0912", "#38202a", "#ff9fb6", "#ff7d9b"),
        "green":   ("#5fd38f", "#7fe0a6", "#062012", "#173326", "#7fe0a6", "#5fd38f"),
        "yellow":  ("#ffcc33", "#ffd966", "#241a00", "#3a3015", "#ffd966", "#ffcc33"),
        "blue":    ("#6ea8ff", "#8fbcff", "#04152e", "#1c2840", "#8fbcff", "#6ea8ff"),
        "red":     ("#ff7a7a", "#ff9999", "#2e0606", "#3b1e1e", "#ff9999", "#ff7a7a"),
        "magenta": ("#f07ad6", "#f59ae1", "#2a0822", "#37202f", "#f59ae1", "#f07ad6"),
    },
}


def palette(mode, accent="pink"):
    """The full color set for 'light'/'dark' with the chosen primary color."""
    p = dict(PALETTES[mode])
    values = ACCENTS[mode].get(accent, ACCENTS[mode]["pink"])
    p.update(zip(("primary", "primary_hover", "on_primary", "primary_soft", "primary_text", "focus"), values))
    return p


# Text size choices: from half size up to double size
FONT_SCALES = (0.5, 0.75, 0.9, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0)

# Segoe Fluent Icons (Windows 11) / Segoe MDL2 Assets (Windows 10) share these code points
ICONS = {
    "back": "", "forward": "", "sync": "", "settings": "",
    "help": "", "info": "", "grid": "", "list": "",
    "search": "", "up": "", "down": "", "check": "",
    "open": "", "sun": "", "moon": "", "auto": "",
    "chev_down": "", "chev_right": "", "error": "", "warning": "",
    "clock": "", "calendar": "", "store": "", "link": "",
    "view": "", "hide": "", "clear": "", "filter": "",
    "library": "", "copy": "", "key": "", "person": "",
    "zoom_in": "", "zoom_out": "", "done": "", "star": "", "done_fill": "", "ring": "", "game": "",
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
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, then old Windows 10)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        flags = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE | NOMOVE | NOZORDER | FRAMECHANGED
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
    except Exception:
        pass


def blend(c1, c2, t):
    """Mix two #rrggbb colors; t=0 gives c1, t=1 gives c2 (used for transitions)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def contrast(c1, c2):
    """WCAG contrast ratio between two #rrggbb colors."""
    def lum(c):
        rgb = []
        for i in (1, 3, 5):
            v = int(c[i:i + 2], 16) / 255
            rgb.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    hi, lo = sorted((lum(c1), lum(c2)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# Base sizes in points at 100%: 4 text sizes (title, heading, body, small) plus icons
FONT_SIZES = {"title": 19, "heading": 13, "body": 10, "body_bold": 10, "small": 9, "small_bold": 9,
              "icon": 11, "icon_big": 28, "mono": 11}


def fonts(root, factor=1.0):
    """Create the app's named fonts at `factor` times the base size."""
    families = set(tkfont.families(root))
    text = "Segoe UI Variable Text" if "Segoe UI Variable Text" in families else "Segoe UI"
    display = "Segoe UI Variable Display" if "Segoe UI Variable Display" in families else text
    icons = "Segoe Fluent Icons" if "Segoe Fluent Icons" in families else "Segoe MDL2 Assets"
    family = {"title": display, "heading": display, "icon": icons, "icon_big": icons, "mono": "Consolas"}
    f = {name: tkfont.Font(root, family=family.get(name, text),
                           weight="bold" if name in ("title", "heading", "body_bold", "small_bold") else "normal")
         for name in FONT_SIZES}
    resize_fonts(root, f, factor)
    return f


def resize_fonts(root, f, factor):
    """Change every font in place; widgets using them update by themselves."""
    for name, size in FONT_SIZES.items():
        f[name].configure(size=max(5, round(size * factor)))
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        tkfont.nametofont(name).configure(family=f["body"].cget("family"), size=max(5, round(10 * factor)))


def apply(root, p, f):
    """Configure every ttk style the app uses for palette `p`."""
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=p["bg"], foreground=p["text"], fieldbackground=p["surface"],
                bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"],
                troughcolor=p["raised"], focuscolor=p["focus"], insertcolor=p["text"],
                selectbackground=p["primary"], selectforeground=p["on_primary"], font=f["body"])

    for prefix, bg in (("", p["bg"]), ("Surface.", p["surface"])):
        s.configure(f"{prefix}TFrame", background=bg)
        s.configure(f"{prefix}TLabel", background=bg, foreground=p["text"], font=f["body"])
        s.configure(f"{prefix}Muted.TLabel", background=bg, foreground=p["muted"], font=f["body"])
        s.configure(f"{prefix}Small.TLabel", background=bg, foreground=p["muted"], font=f["small"])
        s.configure(f"{prefix}Bold.TLabel", background=bg, foreground=p["text"], font=f["body_bold"])
        s.configure(f"{prefix}Title.TLabel", background=bg, foreground=p["text"], font=f["title"])
        s.configure(f"{prefix}Heading.TLabel", background=bg, foreground=p["text"], font=f["heading"])
        s.configure(f"{prefix}Ok.TLabel", background=bg, foreground=p["accent"], font=f["body_bold"])
        s.configure(f"{prefix}Error.TLabel", background=bg, foreground=p["error"], font=f["body"])
        s.configure(f"{prefix}Icon.TLabel", background=bg, foreground=p["muted"], font=f["icon"])

    s.configure("TEntry", fieldbackground=p["surface"], foreground=p["text"],
                bordercolor=p["border_strong"], lightcolor=p["surface"], darkcolor=p["surface"],
                padding=(8, 6))
    s.map("TEntry", bordercolor=[("focus", p["focus"])], lightcolor=[("focus", p["focus"])],
          darkcolor=[("focus", p["focus"])], fieldbackground=[("readonly", p["raised"])])

    s.configure("Vertical.TScrollbar", background=p["raised"], troughcolor=p["bg"],
                bordercolor=p["bg"], arrowcolor=p["muted"], lightcolor=p["raised"],
                darkcolor=p["raised"], gripcount=0, arrowsize=12)
    s.map("Vertical.TScrollbar", background=[("active", p["border_strong"])])
    s.configure("Horizontal.TProgressbar", background=p["primary"], troughcolor=p["raised"],
                bordercolor=p["raised"], lightcolor=p["primary"], darkcolor=p["primary"], thickness=6)
    s.configure("Accent.Horizontal.TProgressbar", background=p["accent"], lightcolor=p["accent"],
                darkcolor=p["accent"])
    s.configure("TSeparator", background=p["border"])

    root.option_add("*Menu.background", p["surface"])
    root.option_add("*Menu.foreground", p["text"])
    root.option_add("*Menu.activeBackground", p["primary"])
    root.option_add("*Menu.activeForeground", p["on_primary"])
