"""
app/services/app_indexer_service.py
Discovers installed apps on startup and stores them in SQLite.

Runs as a background daemon thread — Vasuki is already listening
while indexing happens. Scans targeted locations only (no full C:\\ scan).
Includes Windows Store apps via registry — automatically discovers ALL
Store apps on the machine without any hardcoding.

On every startup: clears and rebuilds the index.
Typical scan time: 3-10 seconds depending on machine.
"""
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.intent_service import normalise

_lock = threading.Lock()
_indexed = False  # True once first scan completes


def _get_db_path() -> str:
    return str(settings.SYSTEM_DB_PATH)


def _ensure_table() -> None:
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_index (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                source TEXT NOT NULL,
                indexed_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()


def _clear_index() -> None:
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("DELETE FROM app_index")
        conn.commit()
        conn.close()


def _insert_app(name: str, path: str, source: str) -> None:
    norm = normalise(name)
    if not norm or len(norm) < 2:
        return
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute(
            "INSERT OR IGNORE INTO app_index (name, path, source) VALUES (?, ?, ?)",
            (norm, path, source)
        )
        conn.commit()
        conn.close()


def _name_from_path(path: str) -> str:
    """Extract display name from file path, removing extension.

    Uses PureWindowsPath (not the OS-native Path) so that Windows-style
    backslash paths are parsed correctly even on Linux/macOS test runners.
    """
    from pathlib import PureWindowsPath
    return PureWindowsPath(path).stem.replace("-", " ").replace("_", " ")


def _scan_lnk_files(directory: str, source: str) -> int:
    """Scan a directory for .lnk shortcut files."""
    count = 0
    try:
        for lnk in Path(directory).rglob("*.lnk"):
            name = _name_from_path(str(lnk))
            # Skip Chrome web app shortcuts — they open in browser not desktop
            if "chrome apps" in str(lnk).lower():
                continue
            _insert_app(name, str(lnk), source)
            count += 1
    except (PermissionError, FileNotFoundError, OSError):
        pass
    return count


def _scan_exe_files(directory: str, source: str, max_depth: int = 2) -> int:
    """Scan a directory for .exe files up to max_depth levels."""
    count = 0
    try:
        base = Path(directory)
        if not base.exists():
            return 0
        pattern = "/".join(["*"] * max_depth) + "/*.exe"
        for exe in base.glob(pattern):
            name = _name_from_path(str(exe))
            _insert_app(name, str(exe), source)
            count += 1
        # Also check direct children
        for exe in base.glob("*.exe"):
            name = _name_from_path(str(exe))
            _insert_app(name, str(exe), source)
            count += 1
    except (PermissionError, FileNotFoundError, OSError):
        pass
    return count


def _scan_store_apps() -> int:
    """
    Scan Windows registry to discover ALL Microsoft Store (UWP) apps.
    Automatically finds WhatsApp, Telegram, Teams, Spotify Store etc.
    No hardcoding — works on every machine regardless of what's installed.
    """
    count = 0
    try:
        import winreg

        friendly_map = {
            "whatsappdesktop": "whatsapp",
            "whatsapp": "whatsapp",
            "telegramdesktop": "telegram",
            "telegram": "telegram",
            "spotifyab": "spotify",
            "spotifymusic": "spotify",
            "spotify": "spotify",
            "instagrambeta": "instagram",
            "instagram": "instagram",
            "discord": "discord",
            "lenovocompanion": "lenovo vantage",
            "unigrampreview": "unigram",
            "unigram": "unigram",
            "adobecreativecloudexpress": "adobe express",
            "clipchamp": "clipchamp",
            "chatgpt": "chatgpt",
            "chatgpt-desktop": "chatgpt",
            "msteams": "teams",
            "microsoftofficehub": "office",
            "outlookforwindows": "outlook",
        }

        skip_pkg_keywords = (
            "microsoftwindows", "windows.internal", "microsoft.net", "microsoft.ui",
            "microsoft.vclibs", "microsoft.winjs", "microsoft.directx", "microsoft.services.store",
            "microsoft.windows.", "microsoft.aad", "microsoft.accountscontrol", "microsoft.async",
            "microsoft.av1", "microsoft.avc", "microsoft.aifabric", "microsoft.advertising",
            "microsoft.credspec", "microsoft.esim", "microsoft.ecapp", "microsoft.lockapp",
            "microsoft.vp9", "microsoft.webp", "microsoft.wpc", "microsoft.bio", "microsoft.xbox",
            "microsoft.zune", "microsoft.bing", "microsoft.54792954", "microsoft.57242383",
            "microsoft.58680125", "microsoft.58681517"
        )

        skip_name_keywords = (
            "packagemetadata", "speechsynthesizer", "taskbar", "systemtray", "fileexplorer",
            "cloudexperience", "speechrecognizer", "livecaptions", "textinput", "experienceextensions",
            "wsxpackmanager", "widgetboard", "widgets", "oobe", "applistbackup", "backupbanner"
        )

        skip_appid_keywords = (
            "packagemetadata", "extension", "global.system", "global.voice", "global.speech",
            "global.fileexplorer", "global.taskbar", "global.systemtray", "global.startmenu",
            "global.widget", "settingsmodelservice", "systemtray", "taskbar", "fileexplorer",
            "cloudexperience", "oobe", "backupbanner", "valuebanner", "twinsxs", "applistbackup"
        )

        registry_paths = [
            (winreg.HKEY_CURRENT_USER,
             r"Software\Classes\Local Settings\Software\Microsoft\Windows"
             r"\CurrentVersion\AppModel\Repository\Packages"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"Software\Classes\Local Settings\Software\Microsoft\Windows"
             r"\CurrentVersion\AppModel\Repository\Packages"),
        ]

        seen_pkgs = set()
        seen_entries = set()

        for hive, reg_path in registry_paths:
            try:
                key = winreg.OpenKey(hive, reg_path)
                i = 0
                while True:
                    try:
                        pkg_name = winreg.EnumKey(key, i)
                        i += 1

                        if pkg_name in seen_pkgs:
                            continue
                        seen_pkgs.add(pkg_name)

                        pkg_lower = pkg_name.lower()

                        # Skip Windows system internal packages
                        if any(sk in pkg_lower for sk in skip_pkg_keywords):
                            continue

                        parts = pkg_name.split(".")
                        if len(parts) >= 2:
                            raw_name = parts[1].split("_")[0]
                        else:
                            raw_name = parts[0].split("_")[0]

                        # Skip names that are pure numbers
                        if raw_name.isdigit():
                            continue

                        # Skip internal system keywords in extracted name
                        if any(sk in raw_name.lower() for sk in skip_name_keywords):
                            continue

                        # Friendly name mapping
                        raw_lower = raw_name.lower()
                        if raw_lower in friendly_map:
                            app_name = friendly_map[raw_lower]
                        else:
                            app_name = (
                                raw_name.replace("Desktop", "")
                                .replace("Beta", "")
                                .replace("Preview", "")
                                .replace("App", "")
                                .replace("Messenger", "")
                                .strip()
                            )

                        if not app_name or len(app_name) < 2:
                            continue

                        try:
                            pkg_key = winreg.OpenKey(key, pkg_name)
                            app_ids = []

                            # Check 'Applications' subkey first if present
                            try:
                                apps_subkey = winreg.OpenKey(pkg_key, "Applications")
                                j = 0
                                while True:
                                    try:
                                        app_ids.append(winreg.EnumKey(apps_subkey, j))
                                        j += 1
                                    except OSError:
                                        break
                                winreg.CloseKey(apps_subkey)
                            except OSError:
                                # Fall back to direct subkeys of pkg_key
                                j = 0
                                while True:
                                    try:
                                        sk = winreg.EnumKey(pkg_key, j)
                                        app_ids.append(sk)
                                        j += 1
                                    except OSError:
                                        break

                            winreg.CloseKey(pkg_key)

                            for app_id in app_ids:
                                app_id_lower = app_id.lower()
                                if any(sk in app_id_lower for sk in skip_appid_keywords):
                                    continue
                                if app_id.isdigit():
                                    continue

                                # PackageFamilyName format: Name_PublisherId (e.g. 5319275A.WhatsAppDesktop_cv1g1gvanyjgm)
                                pkg_parts = pkg_name.split("_")
                                if len(pkg_parts) >= 2 and pkg_parts[0] and pkg_parts[-1]:
                                    family_name = f"{pkg_parts[0]}_{pkg_parts[-1]}"
                                else:
                                    family_name = pkg_name

                                shell_path = f"shell:AppsFolder\\{family_name}!{app_id}"
                                entry_key = (app_name.lower(), shell_path)
                                if entry_key in seen_entries:
                                    continue
                                seen_entries.add(entry_key)

                                _insert_app(app_name, shell_path, "store")
                                count += 1

                        except OSError:
                            pass

                    except OSError:
                        break
                winreg.CloseKey(key)
            except OSError:
                continue

    except Exception:
        pass
    return count


def _scan_registry_mui_cache() -> int:
    """
    Scan MuiCache for recently used apps — catches traditional .exe apps
    that have been run at least once on this machine.
    """
    count = 0
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Shell\MuiCache"
        )
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                if name.lower().endswith(".exe") and Path(name).exists():
                    display = _name_from_path(name)
                    _insert_app(display, name, "registry")
                    count += 1
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass
    return count


def _run_scan() -> None:
    """Full scan — called in background thread."""
    global _indexed
    _ensure_table()
    _clear_index()

    user_home = Path.home()
    total = 0

    # Scan shortcut files (.lnk) — skip Chrome web app shortcuts
    lnk_locations = [
        (str(user_home / "Desktop"), "desktop"),
        (r"C:\Users\Public\Desktop", "desktop"),
        (str(user_home / r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs"),
         "start_menu"),
        (r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs", "start_menu"),
    ]
    for directory, source in lnk_locations:
        total += _scan_lnk_files(directory, source)

    # Scan .exe files in standard install locations
    exe_locations = [
        (r"C:\Program Files", "program_files"),
        (r"C:\Program Files (x86)", "program_files"),
        (str(user_home / r"AppData\Local\Programs"), "appdata"),
        (str(user_home / r"AppData\Local"), "appdata"),
    ]
    for directory, source in exe_locations:
        total += _scan_exe_files(directory, source, max_depth=2)

    # Scan Windows Store apps (UWP) — fully dynamic, no hardcoding
    store_count = _scan_store_apps()
    total += store_count

    # Scan MuiCache for recently used .exe apps
    total += _scan_registry_mui_cache()

    _indexed = True
    print(f"[AppIndex] Scan complete — {total} apps indexed "
          f"({store_count} Store apps).")


def start_indexer() -> None:
    """Start the background indexer thread. Call once on startup."""
    t = threading.Thread(target=_run_scan, daemon=True)
    t.start()


def is_indexed() -> bool:
    """Returns True once the first scan has completed."""
    return _indexed


def find_app(name: str) -> Optional[str]:
    """
    Search the index for an app by normalised name.
    Returns the path/shell string if found, None otherwise.
    Tries exact match first, then prefix match.
    """
    norm = normalise(name)
    if not norm:
        return None
    try:
        with _lock:
            conn = sqlite3.connect(_get_db_path())
            # Exact match first
            row = conn.execute(
                "SELECT path FROM app_index WHERE name = ? LIMIT 1",
                (norm,)
            ).fetchone()
            if not row:
                # Prefix match
                row = conn.execute(
                    "SELECT path FROM app_index WHERE name LIKE ? LIMIT 1",
                    (f"{norm}%",)
                ).fetchone()
            conn.close()
        return row[0] if row else None
    except Exception:
        return None