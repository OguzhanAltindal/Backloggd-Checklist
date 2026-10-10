# Backloggd Checklist

A small desktop app that turns your Steam library into a checklist for logging games on
[Backloggd](https://backloggd.com).

It reads your Steam library through the **official Steam Web API**, matches each game to its
Backloggd page through the **official IGDB API** (Backloggd's own game database, optional), and shows
everything in a list. You open each game's Backloggd page from the app and log it yourself.

## Is my account safe?

- **No passwords, ever.** The app never asks for your Steam, Backloggd or any other login.
- **Official APIs only.** It talks only to `api.steampowered.com` (Steam) and `api.igdb.com` /
  `id.twitch.tv` (IGDB). No scraping, no unofficial endpoints, no browser automation.
- **Read-only.** It only *reads* your Steam library. Nothing is written to Steam, and
  **nothing is ever sent to Backloggd**: you add games yourself.
- **The IGDB token is an app token**, not tied to your Twitch account. It only reads public game data.
- **Your keys are encrypted** with your Windows account (Windows DPAPI) and stored only on this
  computer. The app never shows them in error messages.

Treat your Steam API key like a password: never share it or paste it into a website. If you
think it leaked, revoke it at <https://steamcommunity.com/dev/apikey>.

## Start the app

**Easiest:** double-click **`dist\Backloggd Checklist.exe`**. It's a single file that doesn't need
Python, so you can move it anywhere (Desktop, another PC…).

> Windows may show “Windows protected your PC” the first time, because the exe isn't signed
> with a paid certificate. Click **More info → Run anyway**. You built it yourself from the
> code in this folder.

**From source:** install Python 3.9+ from <https://www.python.org/downloads/> and double-click
**`app.pyw`** (keep it next to `checklist_core.py`).

On first launch the setup wizard opens.

## Rebuild the exe

After changing the code, run this in PowerShell from this folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

It installs PyInstaller into a private `.build-venv` folder (your global Python is untouched),
regenerates `icon.ico`, and writes a new `dist\Backloggd Checklist.exe`.

## First-time setup (inside the app)

On first launch a short setup wizard walks you through everything, one step per screen. You
only need your Steam account. Every link opens the official page, and anything you have to type
into a web page (like `localhost`) has a **Copy** button.

1. **Get your Steam key:** open Steam's key page, paste `localhost` into the *Domain Name* box,
   click *Register* and paste the key back into the app. (Steam only gives keys to accounts that
   have spent at least $5 in the Steam store.)
2. **Your Steam profile:** paste your profile's address and set *Game details* to *Public*.
   The app checks it right away and tells you how many games it found.
3. **Optional, exact Backloggd links:** with a free Twitch developer app (IGDB's official
   access), each game opens its exact Backloggd page. Skip it and each game opens a Backloggd
   search instead. You can turn it on later in **Settings**.

## Using it

1. Click **Sync Steam library**. Your games appear in two groups: **Played** and
   **Not played yet** (games with no playtime, including ones you just bought). Click the box
   next to a group to collapse or expand it; the app remembers your choice. Sort by name,
   playtime or last played with the **Sort** menu or by clicking a column title.
2. Sign in to backloggd.com in your browser as usual.
3. **Double-click** a game (or select it and click **Open on Backloggd**). Its Backloggd page
   opens in your browser: log it there.
4. Press **Space** (or click the ✓ column) to mark it as added. **Hide added** keeps the list short.
5. Games with a **search** link open a Backloggd search: click the right result.
6. Bought new games? Click **Sync Steam library** again. Your marks are kept.

Right-click a game for more options. The **How to use** button shows these steps any time.

## Where data is stored

Everything lives in `%APPDATA%\BackloggdChecklist`: encrypted settings (`config.dat`), your
library (`library.json`), your added marks (`added.json`) and IGDB matches (`igdb_cache.json`).
Delete that folder to reset the app completely.
