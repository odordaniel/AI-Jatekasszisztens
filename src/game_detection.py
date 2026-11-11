"""Offline Windows foreground-game recognition. Never sends screen/audio content."""
import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import re
import threading
import time

_LOCK = threading.RLock()
_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_IGNORE = {'common', 'games', 'game', 'launcher', 'bin', 'binaries', 'shipping',
           'windows', 'system32', 'steam', 'epic games launcher', 'gog galaxy'}


def clean_title(value):
    value = _INVALID.sub('', str(value or '')).strip(' .')[:80]
    return value if len(value) >= 3 and value.casefold() not in _IGNORE else ''


def foreground_process():
    """Read foreground window process image and PID without requiring admin rights."""
    if os.name != 'nt':
        return '', 0
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                        wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return '', 0
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value or pid.value == os.getpid():
            return '', 0
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return '', 0
        try:
            length = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(length.value)
            return (buf.value, pid.value) if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(length)) else ('', 0)
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, ValueError, AttributeError):
        logging.debug('Cannot read foreground executable', exc_info=True)
        return '', 0



def foreground_executable():
    """Compatibility wrapper for callers needing only the executable path."""
    return foreground_process()[0]


def foreground_is_ours():
    """True only when our own UI holds foreground focus."""
    if os.name != 'nt':
        return False
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == os.getpid()
    except (OSError, AttributeError, ValueError):
        return False


def process_is_running(pid):
    """Check whether the recognized game process is still alive."""
    if os.name != 'nt' or not pid:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        # SYNCHRONIZE is sufficient for checking process termination.
        handle = kernel32.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x00000102  # WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError, ValueError):
        return False

def steam_manifest_title(manifest, folder):
    """Match Steam install directory against appmanifest_<appid>.acf metadata."""
    try:
        content = manifest.read_text(encoding='utf-8-sig', errors='replace')
        pairs = dict((key.casefold(), value) for key, value in
                     re.findall(r'^\s*"(name|installdir)"\s+"([^"]+)"', content, re.M | re.I))
        if pairs.get('installdir', '').casefold() == folder.casefold():
            return clean_title(pairs.get('name', ''))
    except OSError:
        pass
    return ''


def epic_manifest_title(executable, manifest_dir=None):
    """Resolve Epic's install manifests by matching their InstallationLocation."""
    if manifest_dir is None:
        base = os.environ.get('PROGRAMDATA', '')
        if not base:
            return ''
        manifest_dir = Path(base) / 'Epic' / 'EpicGamesLauncher' / 'Data' / 'Manifests'
    root = Path(executable)
    try:
        for manifest in Path(manifest_dir).glob('*.item'):
            try:
                info = json.loads(manifest.read_text(encoding='utf-8-sig'))
                location = info.get('InstallLocation')
                if not location:
                    continue
                # Require an actual parent directory, not a string prefix match.
                if root != Path(location) and Path(location) not in root.parents:
                    continue
                return clean_title(info.get('DisplayName', ''))
            except (OSError, ValueError, TypeError):
                continue
    except OSError:
        pass
    return ''


def title_from_path(executable):
    """Determine title only from a verifiable game library path or metadata."""
    if not executable:
        return '', ''
    path = Path(executable)
    # Epic permits custom installation paths, so its manifests take precedence.
    epic_title = epic_manifest_title(executable)
    if epic_title:
        return epic_title, 'Epic'
    parts = path.parts
    lowered = [part.casefold() for part in parts]
    for idx in range(len(parts) - 2):
        if lowered[idx:idx + 2] == ['steamapps', 'common'] and idx + 2 < len(parts) - 1:
            folder = parts[idx + 2]
            steamapps = Path(*parts[:idx + 1])
            for manifest in steamapps.glob('appmanifest_*.acf'):
                title = steam_manifest_title(manifest, folder)
                if title:
                    return title, 'Steam'
            return clean_title(folder), 'Steam mappa'
    for marker, label in (('epic games', 'Epic'), ('gog games', 'GOG'), ('gog galaxy', 'GOG'), ('xboxgames', 'Xbox')):
        if marker in lowered:
            idx = lowered.index(marker)
            if idx + 1 < len(parts) - 1:
                folder = clean_title(parts[idx + 1])
                if folder:
                    return folder, label + ' mappa'
    return '', ''


class GameRecognizer:
    """Local executable mapping + launcher data; cached to avoid repeated disk work."""
    def __init__(self, storage):
        self.storage = Path(storage)
        self._mappings = {}
        self._cache = {}
        self._last_executable = ''
        self.last_polled_executable = ''
        self._last_game_executable = ''
        self._last_game_pid = 0
        self._last_seen = 0.0
        self._load()

    def _load(self):
        with _LOCK:
            try:
                data = json.loads(self.storage.read_text(encoding='utf-8'))
                if isinstance(data, dict):
                    self._mappings = {str(k).casefold(): clean_title(v) for k, v in data.items()
                                      if isinstance(k, str) and isinstance(v, str) and clean_title(v)}
            except FileNotFoundError:
                pass
            except (OSError, UnicodeError, ValueError, TypeError):
                logging.warning('Game mappings invalid; keeping file unchanged')

    def remember(self, executable, title):
        """Explicitly pair a previously observed executable with a game name."""
        title = clean_title(title)
        if not executable or not title:
            return False
        with _LOCK:
            updated = dict(self._mappings)
            updated[str(Path(executable)).casefold()] = title
            try:
                self.storage.parent.mkdir(parents=True, exist_ok=True)
                temp = self.storage.with_suffix('.json.tmp')
                temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
                temp.replace(self.storage)
            except OSError:
                logging.exception('Could not save game pairing')
                return False
            self._mappings = updated
            self._cache.clear()
            return True

    def recognize(self, executable):
        if not executable:
            return '', ''
        key = str(Path(executable)).casefold()
        with _LOCK:
            if key in self._mappings:
                return self._mappings[key], 'saját párosítás'
            # Cache expensive manifest checks but allow new installations to show up.
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < 60:
                return cached[1]
            result = title_from_path(executable)
            self._cache[key] = (time.monotonic(), result)
            return result

    def poll(self):
        exe, pid = foreground_process()
        self.last_polled_executable = exe
        if exe:
            name, source = self.recognize(exe)
            if name:
                self._last_game_executable = exe
                self._last_game_pid = pid
                self._last_executable = exe
                self._last_seen = time.monotonic()
                return name, source
            # Keep the executable for a later user pairing, even if not recognized.
            self._last_executable = exe
            self._last_seen = time.monotonic()
        return '', ''

    def last_running(self):
        """Keep an identified game while our own dialog overlays its window.

        Do not reuse it after the original process exits or another process
        becomes foreground; the caller enforces the foreground constraint.
        """
        if not process_is_running(self._last_game_pid):
            return '', ''
        return self.recognize(self._last_game_executable)

    def recent(self, seconds=15):
        if self._last_executable and time.monotonic() - self._last_seen < seconds:
            return self.recognize(self._last_executable)
        return '', ''

    def pair_recent(self, title, seconds=120):
        if not self._last_executable or time.monotonic() - self._last_seen > seconds:
            return False
        return self.remember(self._last_executable, title)
