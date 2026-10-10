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
- **Official sources only.** It talks only to Steam's official Web API (`api.steampowered.com`),
  Steam's public image server for game pictures, and optionally IGDB's official API
  (`api.igdb.com` / `id.twitch.tv`). No scraping, no unofficial endpoints, no browser automation.
- **Read-only.** It only *reads* your Steam game list. Nothing is changed on Steam, and
  **nothing is ever sent to Backloggd**: you add each game yourself.
- **Your keys stay on your computer**, encrypted with your Windows account. The app never shows
  them in error messages.

Treat your Steam API key like a password: never share it or paste it into a website. If you
think it leaked, revoke it at <https://steamcommunity.com/dev/apikey>.

## First-time setup (inside the app)

The setup opens on first launch and any time from **API keys** at the top right. It shows one step per screen. Every link opens the official page, and anything you have
to type into a web page (like `localhost`) has a **Copy** button.

1. **Get your Steam key:** open Steam's key page, paste `localhost` into the *Domain Name* box,
   click *Register* and paste the key back into the app. (Steam only gives keys to accounts that
   have spent at least $5 in the Steam store.)
2. **Your Steam profile:** paste your profile's address and set *Game details* to *Public*.
   The app checks it right away and tells you how many games it found.
3. **Optional, exact Backloggd links:** with a free Twitch developer app (IGDB's official
   access), each game opens its exact Backloggd page. Skip it and each game opens a Backloggd
   search instead. You can turn it on later from **API keys**.

## Using it

1. Click **Sync library**. Your games appear in two groups: **Played** and **Not played yet**
   (games with no playtime, including ones you just bought). Click a group's title to collapse or
   expand it; the app remembers your choice.
2. The app always opens with your **most recently played** games first. Choose **Grid** (covers)
   or **List** (rows with playtime and last played), and sort by name,
   playtime or last played. Click the active sort again to flip it. For Playtime and Last played,
   **↓** means highest / newest first and **↑** lowest / oldest first. For Name, **↓** means A to Z
   and **↑** Z to A.
3. Rest the mouse on a cover: the lower half fades out and shows your playtime, when you last
   played, and your achievement progress (once you've opened that game's page).
4. Sign in to backloggd.com in your browser as usual, then click **Add to Backloggd** on a game.
   Its Backloggd page opens in your browser, where you add it yourself.
5. Tick the round check mark on a game to mark it as added. **Hide added** keeps the list short.
6. Click a game to open its page: a bigger picture, quick actions and your **Steam achievements**.
7. Everything opens inside the main window. Use the **← →** buttons at the top (or **Alt+← / Alt+→**,
   or your mouse's side buttons) to go back and forward; the library keeps its scroll position,
   search and filters.
8. **Settings** (top right) changes the theme (same as Windows, light or dark), the color (pink, green,
   yellow, blue, red or magenta) and the text size (from half size to double size). Your Steam and IGDB
   keys are under **API keys**, next to it.
9. Bought new games? Click **Sync library** again. Your marks are kept.

Keyboard: **Tab** moves between controls, arrow keys move between games, **Enter** opens a game,
**Space** marks it as added, **A** opens it on Backloggd, **Ctrl+F** searches, **F5** syncs and
**Esc** goes back. The **Help** page in the app lists all of this.

## Where data is stored

Everything lives in `%APPDATA%\BackloggdChecklist`: encrypted settings (`config.dat`), your
library (`library.json`), your added marks (`added.json`), IGDB matches (`igdb_cache.json`), your
view, sort and theme choices (`ui.json`), downloaded game pictures (`images`) and achievements
(`achievements`). Delete that folder to reset the app completely.

---

## For developers

**Run from source:** install Python 3.9+, run `pip install pillow` (for the game pictures), and
double-click `app.pyw`. Keep it next to `checklist_core.py`, `theme.py` and `widgets.py`. The app uses the Segoe UI Variable font and Segoe Fluent Icons that come with Windows 10/11.
Without Pillow the app still works, with placeholders instead of pictures.

**Build the exe:** run this in PowerShell from the repository folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

It installs PyInstaller into a private `.build-venv` folder (your global Python is untouched),
regenerates `icon.ico`, and writes `dist\Backloggd-Checklist.exe`.

**Publish a new version:** on GitHub, go to *Releases → Draft a new release*, create a tag like
`v1.1.0`, attach `dist\Backloggd-Checklist.exe` and click *Publish release*. The download link
above always points to the newest release.
