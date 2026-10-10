# Backloggd Checklist

A small Windows app that turns your Steam library into a checklist for logging games on
[Backloggd](https://backloggd.com). Double-click a game and its Backloggd page opens in your
browser. Log it there, tick it off, move on to the next one.

## ⬇️ Download

1. Go to the **[latest release](../../releases/latest)**.
2. Under **Assets**, click **`Backloggd-Checklist.exe`** to download it.
3. Double-click the downloaded file. That's it: nothing to install, no Python needed.

> **Windows may show “Windows protected your PC”** the first time. This happens with apps from
> small developers that don't pay for a code-signing certificate. Click **More info → Run anyway**.

On first launch a short setup (about 2 minutes) walks you through everything. You only need
your Steam account.

## Is my account safe?

- **No passwords, ever.** The app never asks for your Steam, Backloggd or any other login.
- **Official APIs only.** It talks only to Steam's official Web API (`api.steampowered.com`) and,
  optionally, IGDB's official API (`api.igdb.com` / `id.twitch.tv`). No scraping, no unofficial
  endpoints, no browser automation.
- **Read-only.** It only *reads* your Steam game list. Nothing is changed on Steam, and
  **nothing is ever sent to Backloggd**: you add each game yourself.
- **Your keys stay on your computer**, encrypted with your Windows account. The app never shows
  them in error messages.

Treat your Steam API key like a password: never share it or paste it into a website. If you
think it leaked, revoke it at <https://steamcommunity.com/dev/apikey>.

## First-time setup (inside the app)

The setup shows one step per screen. Every link opens the official page, and anything you have
to type into a web page (like `localhost`) has a **Copy** button.

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
5. Games with a **search** link open a Backloggd search: click the right result. If a page says
   “Page not found”, right-click the game and choose **Search on Backloggd**.
6. Bought new games? Click **Sync Steam library** again. Your marks are kept.

The **How to use** button in the app shows these steps any time.

## Where data is stored

Everything lives in `%APPDATA%\BackloggdChecklist`: encrypted settings (`config.dat`), your
library (`library.json`), your added marks (`added.json`), IGDB matches (`igdb_cache.json`) and
which groups you collapsed (`ui.json`). Delete that folder to reset the app completely.

---

## For developers

**Run from source:** install Python 3.9+ and double-click `app.pyw` (keep it next to
`checklist_core.py`). Only the standard library is used.

**Build the exe:** run this in PowerShell from the repository folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

It installs PyInstaller into a private `.build-venv` folder (your global Python is untouched),
regenerates `icon.ico`, and writes `dist\Backloggd-Checklist.exe`.

**Publish a new version:** on GitHub, go to *Releases → Draft a new release*, create a tag like
`v1.1.0`, attach `dist\Backloggd-Checklist.exe` and click *Publish release*. The download link
above always points to the newest release.
