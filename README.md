# Backloggd Checklist

**Turn your Steam library into a checklist for logging games on [Backloggd](https://backloggd.com).**

A small Windows app: it lists every game you own on Steam, shows what you've played and when, and
opens each game's Backloggd page with one click so you can log it. Tick it off, move on to the next.

## ⬇️ Download

1. Open the **[latest release](../../releases/latest)**.
2. Under **Assets**, download **`Backloggd-Checklist.exe`**.
3. Double-click it. Nothing to install, no Python needed.

Requires **Windows 10 or 11 (64-bit)**.

> **“Windows protected your PC”?** This shows up for apps from small developers without a paid
> code-signing certificate. Click **More info → Run anyway**.

## ✨ Features

- **Your whole Steam library** in two groups: **Played** and **Not played yet**. It opens with your
  most recently played games first.
- **Grid or list view**, sorting by name, playtime or last played, search, and filters.
- **Playtime on hover:** rest the mouse on a cover to see playtime, when you last played and your
  achievement progress.
- **One click to Backloggd:** “Add to Backloggd” opens the game's page in your browser, where you log it.
- **Checklist:** mark games as added and hide them to keep the list short.
- **Game pages** with your **Steam achievements**: what you unlocked, when, and how rare each one is.
- **Your look:** light or dark theme (or same as Windows), 6 colors, text size from 50% to 200%.
- **Easy setup** written for non-technical users, with copy buttons and plain-language checks.
- **Keyboard friendly:** arrows, Enter, Space, Alt+←/→ and more. Works in small and large windows.

## 🔒 Is my account safe?

- **No passwords, ever.** The app never asks for your Steam, Backloggd or any other login.
- **Official sources only:** Steam's Web API (`api.steampowered.com`), Steam's public image server,
  and optionally IGDB's API (`api.igdb.com`). No scraping, no unofficial endpoints, no browser automation.
- **Read-only.** It only *reads* your Steam game list. Nothing is changed on Steam, and **nothing is
  ever sent to Backloggd**: you add each game yourself.
- **Your keys stay on your computer**, encrypted with your Windows account, and never appear in
  error messages.

Treat your Steam API key like a password. If you think it leaked, revoke it at
<https://steamcommunity.com/dev/apikey>.

## 🚀 Getting started

On first launch a short setup (about 2 minutes) walks you through it, one step per screen. You can
open it again any time from **API keys** at the top right.

1. **Steam key:** open Steam's key page, paste `localhost` into *Domain Name* (there's a Copy
   button), click *Register* and paste the key into the app.
   Steam only gives keys to accounts that have spent at least $5 in the Steam store.
2. **Steam profile:** paste your profile's address and set *Game details* to *Public* in Steam's
   privacy settings. The app checks it and tells you how many games it found.
3. **Optional, exact links:** with a free Twitch developer app (IGDB's official access), each game
   opens its exact Backloggd page. Skip it and each game opens a Backloggd search instead.

Then click **Sync library**.

## 📖 Using it

| To… | Do this |
|---|---|
| Log a game on Backloggd | Sign in to backloggd.com in your browser, then click **Add to Backloggd** on the game |
| Mark a game as done | Click the round check mark (or press **Space**) |
| See achievements | Click the game |
| Change the order | Click **Name**, **Playtime** or **Last played**; click again to flip (↑ / ↓) |
| Go back / forward | **←  →** at the top, **Alt+← / Alt+→**, or the mouse side buttons |
| Fix a “Page not found” | Use **Search on Backloggd** on the game's page or in the right-click menu |
| Add newly bought games | Click **Sync library** again; your check marks are kept |
| Change theme, color, text size | **Settings** at the top right |

The **Help** page in the app lists every keyboard shortcut.

## ❓ Troubleshooting

- **“Steam didn't share your game list”:** set *Game details* to *Public* in your Steam privacy settings.
- **“Steam didn't accept this API key”:** copy the key again from Steam's key page; it's 32 letters and numbers.
- **The app doesn't open:** check whether Windows SmartScreen or your antivirus blocked it
  (Windows Security → *Protection history*), and that the download is complete (about 19 MB).
- **Start over:** delete the folder `%APPDATA%\BackloggdChecklist`. It holds the encrypted
  settings, your library, check marks, downloaded pictures and achievements.

---

## 🛠️ For developers

Written in Python with tkinter and Pillow, packaged as a single exe with PyInstaller.

**Run from source** (Python 3.9+):

```bash
pip install pillow
```
```bash
python app.pyw
```

Without Pillow the app still runs, with placeholders instead of pictures. It uses the Segoe UI
Variable font and Segoe Fluent Icons that come with Windows 10/11.

**Build the exe** (PowerShell, from the repository folder):

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

This installs PyInstaller and Pillow into a private `.build-venv` folder and writes
`dist\Backloggd-Checklist.exe`.

| File | What it does |
|---|---|
| `app.pyw` | Main window, pages (library, game, setup, settings, help) and navigation |
| `widgets.py` | Game grid/list, buttons, banners, image loading and animations |
| `theme.py` | Colors, fonts, icons and light/dark styles |
| `checklist_core.py` | Steam and IGDB requests, encrypted settings, local storage |
| `make_icon.py` | Generates `icon.ico` |
| `build.ps1` | Builds the exe |

**Publishing a version:** *Releases → Draft a new release*, create a tag such as `v1.2.0`, attach
`dist\Backloggd-Checklist.exe` and publish. The download link above always points to the newest release.

## License

[MIT](LICENSE): free to use, change and share, as long as the copyright notice is kept.

## Disclaimer

This is an independent fan project. It is not affiliated with or endorsed by Backloggd, Valve/Steam,
IGDB or Twitch. Game names and artwork belong to their respective owners.
