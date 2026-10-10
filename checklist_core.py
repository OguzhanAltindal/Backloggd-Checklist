"""Data layer for Backloggd Checklist: settings, Steam + IGDB sync, local storage.

Only official APIs are used:
  - Steam Web API (IPlayerService/GetOwnedGames), with the user's own API key
  - IGDB API (Twitch client-credentials app token), for matching games to Backloggd
Nothing is ever sent to Backloggd, and no account passwords are ever requested.
"""

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "BackloggdChecklist"
CONFIG_PATH = APP_DIR / "config.dat"
CACHE_PATH = APP_DIR / "igdb_cache.json"
LIBRARY_PATH = APP_DIR / "library.json"
DONE_PATH = APP_DIR / "added.json"

STEAM_API = "https://api.steampowered.com"
IGDB_API = "https://api.igdb.com/v4"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
STEAM_SOURCE_ID = 1  # Steam's id in IGDB's external game source / category
IGDB_BATCH = 500
IGDB_DELAY = 0.3  # IGDB allows 4 requests per second

CONFIG_KEYS = ("steam_api_key", "steam_id", "igdb_client_id", "igdb_client_secret")
REQUIRED_KEYS = ("steam_api_key", "steam_id")  # IGDB is optional: without it games use search links


class SyncError(Exception):
    """An error that is safe to show to the user (secrets already removed)."""


# ---------------------------------------------------------------- secret storage

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _CRYPTPROTECT_UI_FORBIDDEN = 0x1

    def _dpapi(data, encrypt):
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = _Blob()
        fn = _crypt32.CryptProtectData if encrypt else _crypt32.CryptUnprotectData
        if not fn(ctypes.byref(blob_in), None, None, None, None,
                  _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))

    def _protect(data):
        return _dpapi(data, True)

    def _unprotect(data):
        return _dpapi(data, False)

    SECRETS_ENCRYPTED = True
else:
    # No OS keystore available without extra packages; file is still private to the user
    def _protect(data):
        return data

    def _unprotect(data):
        return data

    SECRETS_ENCRYPTED = False


def load_config():
    """Return the saved settings, or None if there are none yet."""
    if not CONFIG_PATH.exists():
        return None
    try:
        raw = _unprotect(base64.b64decode(CONFIG_PATH.read_bytes()))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def save_config(cfg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    data = json.dumps({k: str(cfg.get(k, "")).strip() for k in CONFIG_KEYS}).encode("utf-8")
    CONFIG_PATH.write_bytes(base64.b64encode(_protect(data)))
    if not SECRETS_ENCRYPTED:
        os.chmod(CONFIG_PATH, 0o600)


def config_complete(cfg):
    return bool(cfg) and all(str(cfg.get(k, "")).strip() for k in REQUIRED_KEYS)


def igdb_enabled(cfg):
    return bool(cfg) and bool(cfg.get("igdb_client_id") and cfg.get("igdb_client_secret"))


# ---------------------------------------------------------------- local data

def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def load_library():
    return _read_json(LIBRARY_PATH, {"synced_at": None, "games": []})


def load_done():
    return set(_read_json(DONE_PATH, []))


def save_done(done):
    _write_json(DONE_PATH, sorted(done))


UI_PATH = APP_DIR / "ui.json"


def load_ui():
    return _read_json(UI_PATH, {})


def save_ui(state):
    _write_json(UI_PATH, state)


def backloggd_search_url(game):
    # Slashes break Backloggd's search path (".hack//G.U." gives a 404), and trademark
    # symbols in Steam names don't match Backloggd titles, so search for a cleaned name
    name = game.get("igdb_name") or game["steam_name"]
    name = re.sub(r"[™®©]", "", name)
    name = re.sub(r"[/\\]+", " ", name)
    name = " ".join(name.split())
    return "https://backloggd.com/search/games/" + urllib.parse.quote(name, safe="")


def backloggd_url(game):
    if game.get("slug"):
        return f"https://backloggd.com/games/{urllib.parse.quote(game['slug'], safe='')}/"
    return backloggd_search_url(game)


# ---------------------------------------------------------------- HTTP

def _http_json(url, data=None, headers=None):
    body = data.encode("utf-8") if isinstance(data, str) else data
    req = urllib.request.Request(url, data=body, headers=headers or {})
    req.add_header("User-Agent", "backloggd-checklist/2.0")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------- Steam

def resolve_steam_id(key, steam_id):
    steam_id = steam_id.strip().rstrip("/")
    # Accept a full profile link: take the last path segment
    if "steamcommunity.com" in steam_id:
        steam_id = steam_id.split("/")[-1]
    if re.fullmatch(r"\d{17}", steam_id):
        return steam_id
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", steam_id):
        raise SyncError("That doesn't look like a Steam profile link. Open your Steam profile in "
                        "the browser and copy the whole address, like "
                        "https://steamcommunity.com/id/yourname/")
    q = urllib.parse.urlencode({"key": key, "vanityurl": steam_id})
    data = _http_json(f"{STEAM_API}/ISteamUser/ResolveVanityURL/v1/?{q}")["response"]
    if data.get("success") != 1:
        raise SyncError(f"Couldn't find a Steam profile named “{steam_id}”. "
                        "Copy the whole address of your profile page instead.")
    return data["steamid"]


def fetch_steam_games(key, steam_id):
    q = urllib.parse.urlencode({
        "key": key,
        "steamid": steam_id,
        "include_appinfo": 1,
        "include_played_free_games": 1,
        "format": "json",
    })
    resp = _http_json(f"{STEAM_API}/IPlayerService/GetOwnedGames/v1/?{q}")["response"]
    games = resp.get("games")
    if games is None:
        raise SyncError("Steam didn't share your game list. On your Steam privacy settings page, "
                        "set “Game details” to “Public”, then try again.")
    return games


# ---------------------------------------------------------------- IGDB

def igdb_token(client_id, client_secret):
    # Client-credentials token: an app token only, it grants no access to any user account
    form = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    })
    return _http_json(TWITCH_TOKEN_URL, data=form, headers={
        "Content-Type": "application/x-www-form-urlencoded",
    })["access_token"]


def _igdb_query(endpoint, body, client_id, token):
    time.sleep(IGDB_DELAY)
    return _http_json(f"{IGDB_API}/{endpoint}", data=body, headers={
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })


def match_by_steam_id(appids, client_id, token, progress=None):
    """Return a {steam appid: {name, slug}} mapping."""
    result = {}
    fields = "fields uid, game.name, game.slug;"
    for i in range(0, len(appids), IGDB_BATCH):
        if progress:
            progress(f"Matching with IGDB… {i}/{len(appids)}")
        chunk = appids[i:i + IGDB_BATCH]
        uids = ",".join(f'"{a}"' for a in chunk)
        rows = None
        # Newer IGDB schema uses external_game_source, older one uses category
        for source_field in ("external_game_source", "category"):
            body = f"{fields} where {source_field} = {STEAM_SOURCE_ID} & uid = ({uids}); limit {IGDB_BATCH};"
            try:
                rows = _igdb_query("external_games", body, client_id, token)
                break
            except urllib.error.HTTPError as e:
                if e.code != 400:
                    raise
        for row in rows or []:
            game = row.get("game")
            if isinstance(game, dict) and game.get("slug"):
                result[str(row["uid"])] = {"name": game.get("name"), "slug": game["slug"]}
    return result


# ---------------------------------------------------------------- friendly errors

class _friendly_errors:
    """Turn network errors into SyncError messages without leaking any secret."""

    def __init__(self, *secrets):
        self.secrets = [s for s in secrets if s]

    def redact(self, text):
        for s in self.secrets:
            text = text.replace(s, "***")
        return text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, e, tb):
        if isinstance(e, urllib.error.HTTPError):
            # Never show e.url: Steam requests carry the API key in the query string
            host = urllib.parse.urlparse(e.url).netloc
            if e.code in (401, 403) and "steampowered" in host:
                raise SyncError("Steam didn't accept this API key. Copy it again from the "
                                "Steam key page and make sure nothing is missing.") from None
            if e.code in (400, 401, 403) and ("twitch" in host or "igdb" in host):
                raise SyncError("Twitch didn't accept this Client ID and Secret. Copy them again "
                                "from your app's page on dev.twitch.tv.") from None
            if e.code == 429:
                raise SyncError("Too many requests right now. Wait a minute and try again.") from None
            detail = self.redact(e.read().decode("utf-8", "replace")[:200])
            raise SyncError(f"{host} returned an error ({e.code}). {detail}") from None
        if isinstance(e, urllib.error.URLError):
            raise SyncError("Couldn't connect. Check your internet connection and try again.") from None
        return False


# ---------------------------------------------------------------- setup checks

def check_steam_key_format(key):
    key = key.strip()
    if not key:
        raise SyncError("Paste your Steam key in the box above first.")
    if not re.fullmatch(r"[0-9A-Fa-f]{32}", key):
        raise SyncError("That doesn't look like a Steam key. It's 32 letters and numbers: "
                        "copy everything after “Key:” on the Steam page.")


def check_steam(key, steam_id):
    """Validate Steam settings. Returns (steamid64, number of games)."""
    key, steam_id = key.strip(), steam_id.strip()
    check_steam_key_format(key)
    if not steam_id:
        raise SyncError("Paste your Steam profile link first.")
    with _friendly_errors(key):
        sid = resolve_steam_id(key, steam_id)
        return sid, len(fetch_steam_games(key, sid))


def check_igdb(client_id, client_secret):
    client_id, client_secret = client_id.strip(), client_secret.strip()
    if not client_id or not client_secret:
        raise SyncError("Paste both the Client ID and the Client Secret.")
    with _friendly_errors(client_secret):
        igdb_token(client_id, client_secret)


# ---------------------------------------------------------------- sync

def sync_library(cfg, progress=None):
    """Fetch the Steam library, match it on IGDB if configured, save and return it."""

    def say(msg):
        if progress:
            progress(msg)

    with _friendly_errors(cfg["steam_api_key"], cfg.get("igdb_client_secret")) as guard:
        say("Connecting to Steam…")
        steam_id = resolve_steam_id(cfg["steam_api_key"], cfg["steam_id"])
        say("Fetching your Steam library…")
        games = fetch_steam_games(cfg["steam_api_key"], steam_id)

        cache = _read_json(CACHE_PATH, {})
        todo = [str(g["appid"]) for g in games if str(g["appid"]) not in cache]
        if todo and igdb_enabled(cfg):
            say("Connecting to IGDB…")
            token = igdb_token(cfg["igdb_client_id"], cfg["igdb_client_secret"])
            guard.secrets.append(token)
            found = match_by_steam_id(todo, cfg["igdb_client_id"], token, progress)
            for appid in todo:
                cache[appid] = found.get(appid)  # None = no match, not asked again
            _write_json(CACHE_PATH, cache)

    library = {
        "synced_at": int(time.time()),
        "steam_id": steam_id,
        "games": [{
            "appid": g["appid"],
            "steam_name": g.get("name", f"App {g['appid']}"),
            "igdb_name": (cache.get(str(g["appid"])) or {}).get("name"),
            "slug": (cache.get(str(g["appid"])) or {}).get("slug"),
            "playtime": g.get("playtime_forever", 0),
            "last": g.get("rtime_last_played", 0),
        } for g in games],
    }
    _write_json(LIBRARY_PATH, library)
    return library
