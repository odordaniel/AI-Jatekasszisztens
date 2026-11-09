import base64
import html
import textwrap
import ctypes
import ctypes.wintypes
import re
import io
import json
import os
import sys
import shutil
import logging
import threading
import keyring
import certifi
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import mss
import requests
from PIL import Image
from PySide6.QtCore import QObject, Qt, QThread, Signal, QTimer, QRect, QPoint, QSize, QEvent, QLockFile
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QKeySequence, QShortcut, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QPushButton, QFrame, QLineEdit, QListWidget, QListWidgetItem, QComboBox, QTextEdit, QSizeGrip, QGraphicsDropShadowEffect, QAbstractItemView, QSizePolicy, QCheckBox, QSystemTrayIcon, QMenu, QMessageBox, QSpinBox, QScrollArea

# A telepített program minden felhasználói fájlt a saját AppData könyvtárába ment.
APP_DIR = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')) / 'AIJatekasszisztens'
APP_DIR.mkdir(parents=True, exist_ok=True)
ROOT = APP_DIR
CONFIG_PATH = ROOT / 'config.json'
APP_VERSION = '1.9.3'  # Update when publishing the next release

# Első indításkor áthozzuk a meglévő parancssoros kiadás beállításait és előzményeit.
def migrate_previous_install():
    candidates = [Path(sys.executable).resolve().parent, Path(__file__).resolve().parent,
                  Path.home() / 'Downloads' / 'Windows11_AI_Jatekasszisztens']
    for filename in ('config.json', 'forditasok.json', 'forditas_mappak.json',
                     'ablak_beallitasok.json', 'caddy-root.crt'):
        dst = ROOT / filename
        if dst.exists():
            continue
        for folder in candidates:
            src = folder / filename
            if src.is_file() and src.resolve() != dst.resolve():
                try:
                    shutil.copy2(src, dst)
                    break
                except OSError:
                    logging.exception('Régi beállítás átvétele sikertelen: %s', filename)


def tls_verify_for(url):
    """Public endpoints use the standard CA bundle; internal Caddy hosts use the optional private CA."""
    host = (urlsplit(url).hostname or '').lower()
    ca = ROOT / 'caddy-root.crt'
    if host.endswith('.home.arpa') and ca.is_file():
        return str(ca)
    return certifi.where()


def validate_api_url(value):
    """Prevent accidental unencrypted remote API-key or screenshot transmission."""
    url = value.strip()
    p = urlsplit(url)
    if p.username or p.password or p.query or p.fragment or not p.hostname:
        raise ValueError('A végpont URL-je nem tartalmazhat felhasználót, jelszót, queryt vagy fragmentet.')
    if p.scheme != 'https' and not (p.scheme == 'http' and p.hostname in ('127.0.0.1', '::1', 'localhost')):
        raise ValueError('Távoli szolgáltatáshoz HTTPS szükséges; HTTP csak localhost lehet.')
    if not p.path.endswith('/chat/completions'):
        raise ValueError('A végpontnak /chat/completions útvonalra kell végződnie.')
    if p.port is not None and not 1 <= p.port <= 65535:
        raise ValueError('Érvénytelen port.')
    return url


VAULT_SERVICE = 'AIJatekasszisztens'
VAULT_USERNAME = 'translation-api-key'


def save_api_key(secret):
    """Windows Credential Manager, encrypted per Windows account."""
    if secret:
        keyring.set_password(VAULT_SERVICE, VAULT_USERNAME, secret)
    else:
        try:
            keyring.delete_password(VAULT_SERVICE, VAULT_USERNAME)
        except keyring.errors.PasswordDeleteError:
            pass


def read_api_key():
    return keyring.get_password(VAULT_SERVICE, VAULT_USERNAME) or ''


def write_config(config):
    # Never serialize the in-memory secret in plaintext.
    sanitized = {k: v for k, v in config.items() if k not in ('api_key', 'api_key_dpapi')}
    temp = CONFIG_PATH.with_suffix('.json.tmp')
    temp.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(CONFIG_PATH)


def icon_path():
    # PyInstaller --onedir esetén a támogatott erőforrásútvonal.
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return base / 'app.ico'

DEFAULTS = {
    'api_url': 'http://127.0.0.1:8080/api/chat/completions',
    'api_key': '', 'model': '', 'fallback_model': '',
    'max_image_width': 1600,
    'hotkeys': {'select': 'Ctrl+Shift+T', 'center': '', 'history': 'Ctrl+Shift+H', 'quit': 'Ctrl+Shift+Q'},
    'fps_width_percent': 55, 'fps_height_percent': 40,
}


def load_config():
    if not CONFIG_PATH.exists():
        write_config(DEFAULTS)
    raw = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    if not isinstance(raw, dict):
        raise ValueError('A config.json érvénytelen.')
    data = DEFAULTS.copy()
    data.update(raw)
    legacy_key = str(raw.get('api_key') or '')
    if legacy_key:
        # Migration only removes the plaintext after Credential Manager successfully stores it.
        save_api_key(legacy_key)
        write_config(data)
        logging.warning('Legacy API key migrated from config.json into Windows Credential Manager.')
    try:
        data['hotkeys'] = normalize_hotkeys(data.get('hotkeys'))
    except ValueError as exc:
        logging.warning('Invalid saved hotkeys, restoring defaults: %s', exc)
        data['hotkeys'] = dict(HOTKEY_DEFAULTS)
    data['api_key'] = read_api_key()
    return data



# WM_MBUTTONDOWN (Mouse3) and XBUTTON1 / XBUTTON2 (Mouse4/Mouse5)
# are supported. The hook never consumes input and ignores injected events. Some anti-cheat systems
# may restrict global hooks or desktop capture.
ACTION_NAMES = {'select': 'Terület kijelölése', 'center': 'FPS: középső terület fordítása',
                'history': 'Előzmények', 'quit': 'Ablak bezárása / kijelölés megszakítása'}
HOTKEY_DEFAULTS = {'select': 'Ctrl+Shift+T', 'center': '',
                   'history': 'Ctrl+Shift+H', 'quit': 'Ctrl+Shift+Q'}
KEY_NAMES = {'SPACE': 0x20, 'TAB': 0x09, 'INSERT': 0x2D, 'DELETE': 0x2E,
             'HOME': 0x24, 'END': 0x23, 'PAGEUP': 0x21, 'PAGEDOWN': 0x22,
             'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27}


def parse_hotkey(raw):
    """Return canonical name and keyboard (mods,vk) or mouse (mods, XBUTTON)."""
    value = (raw or '').strip()
    if not value:
        return '', None
    parts = [x.strip() for x in value.split('+')]
    if any(not x for x in parts) or len(parts) > 4:
        raise ValueError('Hibás gyorsbillentyű: ' + value)
    aliases = {'CONTROL': 'CTRL', 'WIN': 'WIN', 'WINDOWS': 'WIN',
               'ALT': 'ALT', 'SHIFT': 'SHIFT', 'CTRL': 'CTRL',
               'XBUTTON1': 'MOUSE4', 'XBUTTON2': 'MOUSE5',
               'MBUTTON': 'MOUSE3', 'MIDDLEBUTTON': 'MOUSE3', 'MIDDLE': 'MOUSE3'}
    mods = 0
    names = []
    for x in parts[:-1]:
        v = aliases.get(x.upper(), x.upper())
        if v not in ('CTRL', 'ALT', 'SHIFT', 'WIN') or v in names:
            raise ValueError('Hibás módosítóbillentyű: ' + value)
        names.append(v)
        mods |= {'ALT': 1, 'CTRL': 2, 'SHIFT': 4, 'WIN': 8}[v]
    last = aliases.get(parts[-1].upper(), parts[-1].upper())
    order = ['CTRL', 'ALT', 'SHIFT', 'WIN']
    prefix = [v.title() if v != 'CTRL' else 'Ctrl' for v in order if v in names]
    if last in ('MOUSE3', 'MOUSE4', 'MOUSE5'):
        mouse_id = {'MOUSE3': 0, 'MOUSE4': 1, 'MOUSE5': 2}[last]
        return '+'.join(prefix + [f'Mouse{mouse_id + 3}']), ('mouse', mods, mouse_id)
    if len(last) == 1 and last in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':
        vk = ord(last)
    elif re.fullmatch(r'F(?:[1-9]|1[0-9]|2[0-4])', last):
        vk = 0x70 + int(last[1:]) - 1
    elif last in KEY_NAMES:
        vk = KEY_NAMES[last]
    elif re.fullmatch(r'VK_[0-9A-F]{2}', last):
        vk = int(last[3:], 16)
        if vk < 0x08 or vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xFF):
            raise ValueError('Nem rendelhető hozzá ez a billentyű.')
    else:
        raise ValueError('Nem támogatott billentyű: ' + value)
    return '+'.join(prefix + [last.title() if last in KEY_NAMES else last]), ('key', mods, vk)


def normalize_hotkeys(values):
    raw = dict(HOTKEY_DEFAULTS)
    if isinstance(values, dict):
        raw.update({k: v for k, v in values.items() if k in raw and isinstance(v, str)})
    normalized = {}
    used = {}
    for action in ACTION_NAMES:
        name, spec = parse_hotkey(raw[action])
        if spec is not None:
            if spec in used:
                raise ValueError(f'Azonos gyorsbillentyű: {ACTION_NAMES[used[spec]]} és {ACTION_NAMES[action]}')
            used[spec] = action
        normalized[action] = name
    return normalized


# Native key events are used for binding recording. Extra buttons reported by
# Windows as MiddleButton/XBUTTON1/XBUTTON2 are supported; vendor-specific extra buttons are not
# standardized and may need to be mapped to keyboard keys in mouse software.
def captured_key_name(vk):
    if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return 'F' + str(vk - 0x70 + 1)
    for name, value in KEY_NAMES.items():
        if value == vk:
            return name.title()
    if 0x08 <= vk <= 0xFE:
        return f'VK_{vk:02X}'
    return ''


def modifiers_to_prefix(mods):
    return [name for flag, name in ((2, 'Ctrl'), (1, 'Alt'), (4, 'Shift'), (8, 'Win')) if mods & flag]


class ShortcutRecorder(QLineEdit):
    """Capture a key combination, middle mouse, or standard side-mouse button."""
    capture_started = Signal()
    capture_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setPlaceholderText('Kattints ide a rögzítéshez')
        self.setToolTip('Kattints, majd nyomj le egy gombot vagy kombinációt. Esc: mégse; Backspace: törlés.')
        self.recording = False
        self.previous = ''

    def start_recording(self):
        if self.recording:
            return
        self.previous = self.text()
        self.recording = True
        self.setText('Nyomj le egy billentyűt vagy egérgombot (Mouse3/4/5)…')
        self.setProperty('recording', True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        QApplication.instance().installEventFilter(self)
        self.capture_started.emit()

    def stop_recording(self, new_value=None):
        if not self.recording:
            return
        QApplication.instance().removeEventFilter(self)
        self.recording = False
        self.setProperty('recording', False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(self.previous if new_value is None else new_value)
        self.capture_finished.emit()

    def mousePressEvent(self, event):
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.XButton1, Qt.MouseButton.XButton2):
            if not self.recording:
                self.start_recording()
            self._record_mouse(event.button(), event.modifiers())
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_recording()
            event.accept()
            return
        super().mousePressEvent(event)

    def _record_mouse(self, button, modifiers):
        mods = self._mods(modifiers)
        name = ('Mouse3' if button == Qt.MouseButton.MiddleButton
                else 'Mouse4' if button == Qt.MouseButton.XButton1 else 'Mouse5')
        self._record('+'.join(modifiers_to_prefix(mods) + [name]))

    @staticmethod
    def _mods(modifiers):
        result = 0
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            result |= 2
        if modifiers & Qt.KeyboardModifier.AltModifier:
            result |= 1
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            result |= 4
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            result |= 8
        return result

    def _record(self, raw):
        try:
            normalized, _ = parse_hotkey(raw)
        except ValueError:
            return
        self.stop_recording(normalized)

    def eventFilter(self, watched, event):
        if not self.recording:
            return False
        if event.type() == QEvent.Type.KeyPress:
            if event.isAutoRepeat():
                return True
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.stop_recording()
                return True
            if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                self.stop_recording('')
                return True
            vk = event.nativeVirtualKey()
            if not vk:
                # Some Qt plugins do not expose nativeVirtualKey for all keys.
                qt_key = int(key)
                if 0x20 <= qt_key <= 0x7E:
                    vk = qt_key
                elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
                    vk = 0x70 + qt_key - int(Qt.Key.Key_F1)
                else:
                    vk = {int(Qt.Key.Key_Up): 0x26, int(Qt.Key.Key_Down): 0x28,
                          int(Qt.Key.Key_Left): 0x25, int(Qt.Key.Key_Right): 0x27,
                          int(Qt.Key.Key_PageUp): 0x21, int(Qt.Key.Key_PageDown): 0x22}.get(qt_key, 0)
            if vk in (0x10, 0x11, 0x12, 0x5B, 0x5C):
                return True
            name = captured_key_name(vk)
            if not name:
                return True
            mods = self._mods(event.modifiers())
            self._record('+'.join(modifiers_to_prefix(mods) + [name]))
            return True
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.XButton1, Qt.MouseButton.XButton2):
                self._record_mouse(event.button(), event.modifiers())
                return True
            if watched is not self and event.button() == Qt.MouseButton.LeftButton:
                self.stop_recording()
        return False

    def keyPressEvent(self, event):
        if self.recording:
            self.eventFilter(self, event)
            return
        super().keyPressEvent(event)


# Privacy and performance: no idle screen-capture thread.
# RegionSelector captures the screen only after an explicit translation request.


class Translator(QThread):
    finished_text = Signal(str)
    model_started = Signal(str, bool)

    def __init__(self, image_bytes, cfg):
        super().__init__()
        self.image_bytes = image_bytes
        self.cfg = cfg

    def run(self):
        try:
            cfg = dict(self.cfg)
            url = cfg['api_url'].strip()
            url = validate_api_url(url)
            models = [cfg.get('model', '').strip()]
            fallback = cfg.get('fallback_model', '').strip()
            if not models[0]:
                raise ValueError('Állíts be elsődleges modellt a Beállítások oldalon.')
            if fallback and fallback != models[0]:
                models.append(fallback)
            headers = {'Content-Type': 'application/json'}
            if cfg.get('api_key', '').strip():
                headers['Authorization'] = f"Bearer {cfg['api_key'].strip()}"
            if not self.image_bytes or len(self.image_bytes) > 12 * 1024 * 1024:
                raise ValueError('A kijelölt kép üres vagy túl nagy (maximum 12 MB).')
            encoded = base64.b64encode(self.image_bytes).decode('ascii')
            messages = [{'role': 'user', 'content': [
                {'type': 'text', 'text': (
                    'Fordítsd magyarra a képen látható videojáték-szövegeket. '
                    'Őrizd meg a jelentést, a neveket és a játék kontextusát. '
                    'Csak a fordítást add vissza, röviden. '
                    'Ha nincs olvasható szöveg, írd: Nincs fordítható szöveg.')},
                {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + encoded}}
            ]}]
            errors = []
            with requests.Session() as session:
                # Prevent system proxy and CA environment variables from silently rerouting private screenshots.
                session.trust_env = False
                for index, model in enumerate(models):
                    self.model_started.emit(model, index > 0)
                    try:
                        # Stream and cap the response before parsing to avoid unbounded allocations.
                        with session.post(
                            url, json={'model': model, 'stream': False, 'messages': messages},
                            headers=headers, timeout=(10, 65), allow_redirects=False,
                            verify=tls_verify_for(url), stream=True,
                        ) as response:
                            if response.is_redirect:
                                raise ValueError('Az API átirányítást kért; biztonsági okból elutasítva.')
                            if response.status_code in (401, 403, 413, 422):
                                self.finished_text.emit(
                                    f'Fordítási hiba: HTTP {response.status_code}. '
                                    'Ellenőrizd az API-kulcsot, a jogosultságokat és a kérés formátumát.')
                                return
                            if response.status_code >= 400:
                                errors.append(f'{model}: HTTP {response.status_code}')
                                continue
                            chunks = []
                            total = 0
                            for part in response.iter_content(chunk_size=65536):
                                total += len(part)
                                if total > 4 * 1024 * 1024:
                                    raise ValueError('Az AI-válasz túl nagy.')
                                chunks.append(part)
                            body = json.loads(b''.join(chunks).decode('utf-8'))
                        result = body['choices'][0]['message']['content']
                        if isinstance(result, list):
                            result = '\n'.join(piece.get('text', '') for piece in result if isinstance(piece, dict))
                        result = str(result or '').strip()
                        if not result:
                            raise ValueError('A modell üres választ adott.')
                        if index:
                            logging.info('Fallback model used.')
                        self.finished_text.emit(result[:20000])
                        return
                    except requests.exceptions.SSLError:
                        raise ValueError('A HTTPS-tanúsítvány nem ellenőrizhető. Ellenőrizd a Caddy CA fájlt.')
                    except requests.exceptions.Timeout:
                        errors.append(f'{model}: időtúllépés')
                    except requests.RequestException:
                        errors.append(f'{model}: hálózati hiba')
                    except (KeyError, IndexError, TypeError, ValueError) as exc:
                        # Do not place raw URLs, headers or API responses into error messages.
                        errors.append(f'{model}: hibás vagy nem támogatott API-válasz')
                    if index == 0 and len(models) > 1:
                        logging.info('Primary model failed; trying fallback.')
            raise RuntimeError(' | '.join(errors))
        except Exception as exc:
            self.finished_text.emit(f'Fordítási hiba: {str(exc)[:600]}')


# API discovery is deliberately read-only: no screenshot and no paid inference request.
def models_endpoint(chat_url):
    chat_url = validate_api_url(chat_url)
    parts = urlsplit(chat_url)
    base = chat_url[:-len('/chat/completions')]
    if parts.path.endswith('/api/chat/completions'):
        return chat_url[:-len('/api/chat/completions')] + '/api/models'
    return base + '/models'


def fetch_available_models(chat_url, api_key):
    url = models_endpoint(chat_url)
    headers = {'Accept': 'application/json'}
    if api_key.strip():
        headers['Authorization'] = 'Bearer ' + api_key.strip()
    with requests.Session() as session:
        session.trust_env = False
        with session.get(url, headers=headers, timeout=(7, 18), verify=tls_verify_for(url),
                         allow_redirects=False, stream=True) as response:
            if response.is_redirect:
                raise ValueError('A modelllista végpontja átirányítást kért.')
            if response.status_code in (401, 403):
                raise ValueError(f'HTTP {response.status_code}: API-kulcs vagy jogosultság hiba.')
            if response.status_code == 404:
                raise ValueError('HTTP 404: a szolgáltató nem támogatja a modelllista-végpontot.')
            if response.status_code >= 400:
                raise ValueError(f'HTTP {response.status_code}: nem sikerült lekérni a modelleket.')
            body_bytes = bytearray()
            for chunk in response.iter_content(chunk_size=32768):
                body_bytes.extend(chunk)
                if len(body_bytes) > 2 * 1024 * 1024:
                    raise ValueError('A modelllista túl nagy.')
            data = json.loads(body_bytes.decode('utf-8'))
    if isinstance(data, dict):
        entries = data.get('data', data.get('models'))
    elif isinstance(data, list):
        entries = data
    else:
        entries = None
    if not isinstance(entries, list):
        raise ValueError('A modelllista válaszának formátuma nem támogatott.')
    ids = set()
    for item in entries:
        if isinstance(item, dict):
            model_id = item.get('id') or item.get('name')
        elif isinstance(item, str):
            model_id = item
        else:
            continue
        if isinstance(model_id, str) and model_id.strip() and len(model_id) <= 200:
            ids.add(model_id.strip())
    return sorted(ids, key=str.casefold)


class ModelDiscovery(QThread):
    result = Signal(object)

    def __init__(self, url, api_key):
        super().__init__()
        self.url = url
        self.api_key = api_key

    def run(self):
        try:
            ids = fetch_available_models(self.url, self.api_key)
            self.result.emit({'ok': True, 'models': ids})
        except requests.exceptions.SSLError:
            self.result.emit({'ok': False, 'error': 'HTTPS-tanúsítvány hiba. Ellenőrizd a Caddy CA-t.'})
        except requests.exceptions.Timeout:
            self.result.emit({'ok': False, 'error': 'Időtúllépés a modelllista lekérésekor.'})
        except requests.RequestException:
            self.result.emit({'ok': False, 'error': 'Hálózati hiba vagy nem elérhető API.'})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.result.emit({'ok': False, 'error': str(exc)[:200]})
        except Exception:
            logging.exception('Model discovery failed')
            self.result.emit({'ok': False, 'error': 'Váratlan hiba a modelllista lekérésekor.'})


HISTORY_PATH = ROOT / 'forditasok.json'
FOLDERS_PATH = ROOT / 'forditas_mappak.json'


class HistoryStore:
    def __init__(self):
        self.items = []
        self.folders = []
        if FOLDERS_PATH.exists():
            try:
                loaded_folders = json.loads(FOLDERS_PATH.read_text(encoding='utf-8'))
                if isinstance(loaded_folders, list):
                    self.folders = [x for x in loaded_folders if isinstance(x, str) and x.strip()]
                    self.folders = list(dict.fromkeys(self.folders))
            except (OSError, ValueError) as exc:
                logging.warning('Mappák betöltési hiba: %s', type(exc).__name__)
        if HISTORY_PATH.exists():
            try:
                loaded = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
                if isinstance(loaded, list):
                    self.items = [x for x in loaded if isinstance(x, dict) and isinstance(x.get('text'), str)]
            except (OSError, ValueError) as exc:
                logging.warning('Előzmények betöltési hiba: %s', type(exc).__name__)

    def save_folders(self):
        try:
            tmp = FOLDERS_PATH.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(self.folders, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(FOLDERS_PATH)
            return True
        except OSError as exc:
            logging.warning('Mappák mentési hiba: %s', type(exc).__name__)
            return False

    def create_folder(self, name):
        name = name.strip()
        if not name or len(name) > 80 or name.casefold() == 'összes' or any(x.casefold() == name.casefold() for x in self.folders):
            return False
        self.folders.append(name)
        if not self.save_folders():
            self.folders.pop()
            return False
        return True

    def rename_folder(self, old, new):
        new = new.strip()
        if old not in self.folders or not new or len(new) > 80 or new.casefold() == 'összes':
            return False
        if any(x.casefold() == new.casefold() for x in self.folders if x != old):
            return False
        original = [dict(x) for x in self.items]
        self.items = [dict(x, folder=new) if x.get('folder') == old else x for x in self.items]
        pos = self.folders.index(old)
        self.folders[pos] = new
        if not self.save() or not self.save_folders():
            self.items = original
            self.folders[pos] = old
            self.save()
            self.save_folders()
            return False
        return True

    def delete_folder(self, name):
        # Folder deletion never deletes its translations; they move to 'Unsorted'.
        if name not in self.folders:
            return False
        original = [dict(x) for x in self.items]
        self.items = [dict(x, folder='') if x.get('folder') == name else x for x in self.items]
        self.folders.remove(name)
        if not self.save() or not self.save_folders():
            self.items = original
            self.folders.append(name)
            self.save()
            self.save_folders()
            return False
        return True

    def update_item(self, index, **changes):
        if not 0 <= index < len(self.items):
            return False
        old = dict(self.items[index])
        self.items[index] = dict(old, **changes)
        if not self.save():
            self.items[index] = old
            return False
        return True

    def add(self, value):
        if not value.strip() or value.startswith('Fordítási hiba:') or value == 'Nincs fordítható szöveg.':
            return
        self.items.append({'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'text': value})
        self.save()

    def save(self):
        try:
            tmp = HISTORY_PATH.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(HISTORY_PATH)
            return True
        except OSError as exc:
            logging.warning('Előzmények mentési hiba: %s', type(exc).__name__)
            return False

    def delete(self, index):
        if not 0 <= index < len(self.items):
            return False
        removed = self.items.pop(index)
        if not self.save():
            self.items.insert(index, removed)
            return False
        return True

    def clear(self):
        original = self.items
        self.items = []
        if not self.save():
            self.items = original
            return False
        return True


class Overlay(QWidget):
    """Resizable, persistent, single-window translation UI."""

    WINDOW_PATH = ROOT / 'ablak_beallitasok.json'

    STYLE = """
    QWidget#rootPanel { background: #111827; border: 1px solid #344256; border-radius: 16px; }
    QWidget#historyPanel { background: #192337; border: 1px solid #29384e; border-radius: 12px; }
    QLabel { color: #e9f0fa; background: transparent; }
    QLabel#brand { font-size: 16px; font-weight: 700; color: #f2f7ff; }
    QLabel#small { font-size: 11px; color: #90a5bf; }
    QLabel#section { font-size: 12px; font-weight: 700; color: #c9d7ed; }
    QLabel#status { font-size: 11px; color: #95baf6; }
    QTextEdit#translation { background: #172236; border: 1px solid #2b3b52;
        border-radius: 11px; color: #eff5ff; padding: 11px; font-size: 14px;
        selection-background-color: #346b9c; }
    QPushButton { background: #253348; border: 1px solid #354962;
        color: #e7f0fb; border-radius: 8px; padding: 6px 10px;
        font-size: 12px; font-weight: 500; min-height: 22px; }
    QPushButton:hover { background: #344863; border-color: #5578a4; }
    QPushButton:pressed { background: #1d2c40; }
    QPushButton:disabled { color: #6e8198; background: #1d2a3b; border-color: #29384b; }
    QPushButton[role="primary"] { background: #245eaa; border-color: #377ac9; color: white; }
    QPushButton[role="primary"]:hover { background: #2c70c4; }
    QPushButton[role="danger"] { color: #ffc5c5; border-color: #7c434c; background: #472833; }
    QPushButton[role="danger"]:hover { background: #66313b; }
    QPushButton[role="top"] { min-width: 27px; max-width: 32px; min-height: 28px;
        border-radius: 10px; background: transparent; border: 1px solid transparent;
        font-size: 17px; padding: 3px; color: #b7c7df; }
    QPushButton[role="top"]:hover { background: #26364f; border-color: #405779; color: white; }
    QPushButton[role="topActive"] { min-width: 27px; max-width: 32px; min-height: 28px;
        border-radius: 10px; background: #264b77; border: 1px solid #376da9;
        color: #ffffff; font-size: 17px; padding: 3px; }
    QFrame#settingsPanel { background: #192337; border: 1px solid #304057; border-radius: 12px; }
    QCheckBox { color: #dce8f8; spacing: 8px; }
    QPushButton[role="icon"] { min-width: 25px; max-width: 35px; font-size: 17px; padding: 5px; }
    QLineEdit, QComboBox { background: #101a2a; color: #ecf3fb;
        border: 1px solid #3d526e; border-radius: 8px; padding: 7px;
        selection-background-color: #2b6ab4; font-size: 12px; min-height: 19px; }
    QLineEdit:focus, QComboBox:focus { border: 1px solid #6faef5; }
    QComboBox QAbstractItemView { background: #182338; color: white;
        selection-background-color: #2c5f98; }
    QListWidget { background: #111d2e; border: 1px solid #31435c; border-radius: 9px;
        color: #e6f0fc; font-size: 12px; outline: none; padding: 4px; }
    QListWidget::item { padding: 9px 7px; border-radius: 6px; }
    QListWidget::item:selected { background: #2c5a91; color: white; }
    QListWidget::item:hover { background: #253b58; }
    QScrollBar:vertical { background: #172337; width: 10px; margin: 2px; }
    QScrollBar::handle:vertical { background: #456080; border-radius: 4px; min-height: 22px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    """

    def __init__(self, cfg, history):
        super().__init__()
        self.cfg = cfg
        self.history = history
        self.history_index = None
        self.drag_start = None
        self.pending_delete = None
        self.edit_action = None
        self.edit_index = None
        self.edit_folder = None
        self._restoring_geometry = True
        self._history_before_settings = False
        # User preference is independent from temporary hiding during translation.
        self._history_preference = False
        self._mode_switching = False
        self._compact_size = QSize(660, 370)
        self._history_size = QSize(660, 680)
        self._settings_size = QSize(660, 680)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(465, 250)
        self.setWindowTitle('AI Játékasszisztens')

        self.geometry_timer = QTimer(self)
        self.geometry_timer.setSingleShot(True)
        self.geometry_timer.setInterval(500)
        self.geometry_timer.timeout.connect(self.save_geometry)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(13, 13, 13, 13)
        self.panel = QFrame(self)
        self.panel.setObjectName('rootPanel')
        self.panel.setStyleSheet(self.STYLE)
        outer.addWidget(self.panel)
        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 155))
        self.panel.setGraphicsEffect(shadow)
        content = QVBoxLayout(self.panel)
        content.setContentsMargins(16, 13, 16, 10)
        content.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.handle = QLabel('◈  AI Játékasszisztens')
        self.handle.setObjectName('brand')
        self.handle.setToolTip('Húzd innen az ablak áthelyezéséhez')
        self.handle.setCursor(Qt.CursorShape.SizeAllCursor)
        self.handle.installEventFilter(self)
        header.addWidget(self.handle, 1)
        self.prev_button = self.btn('‹', lambda: self.navigate(-1), 'Előző fordítás', role='top')
        self.next_button = self.btn('›', lambda: self.navigate(1), 'Következő fordítás', role='top')
        self.history_button = self.btn('☷', self.open_history, 'Mentett fordítások és keresés', role='top')
        self.settings_button = self.btn('⚙', self.toggle_settings, 'API és modell beállításai', role='top')
        self.close_button = self.btn('×', self.hide, 'Ablak bezárása', role='top')
        for widget in (self.prev_button, self.next_button, self.history_button):
            header.addWidget(widget)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet('background: #334158; border: 0;')
        separator.setFixedSize(1, 21)
        header.addWidget(separator)
        header.addWidget(self.settings_button)
        header.addWidget(self.close_button)
        content.addLayout(header)

        self.subtitle = QLabel('MAGYAR FORDÍTÁS   •   Kijelölés vagy FPS-gyorsfordítás')
        self.subtitle.setObjectName('small')
        content.addWidget(self.subtitle)
        self.label = QTextEdit()
        self.label.setObjectName('translation')
        self.label.setReadOnly(True)
        self.label.setAcceptRichText(False)
        self.label.setPlaceholderText('Itt fog megjelenni a kijelölt játékbeli szöveg fordítása.')
        self.label.setMinimumHeight(75)
        content.addWidget(self.label, 1)

        # Settings live within the same draggable window; no modal dialogs.
        self.settings_panel = QScrollArea()
        self.settings_panel.setWidgetResizable(True)
        self.settings_panel.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_panel.setStyleSheet('QScrollArea {background: transparent; border: 0;}')
        self.settings_content = QFrame()
        self.settings_content.setObjectName('settingsPanel')
        self.settings_panel.setWidget(self.settings_content)
        settings_layout = QVBoxLayout(self.settings_content)
        settings_layout.setContentsMargins(19, 18, 19, 17)
        settings_layout.setSpacing(10)
        settings_heading = QLabel('Kapcsolat és modellek')
        settings_heading.setObjectName('brand')
        settings_header = QHBoxLayout()
        settings_header.addWidget(settings_heading)
        settings_header.addStretch()
        self.version_label = QLabel(f'v{APP_VERSION}')
        self.version_label.setObjectName('small')
        self.version_label.setToolTip('Alkalmazásverzió')
        settings_header.addWidget(self.version_label)
        settings_layout.addLayout(settings_header)
        settings_description = QLabel('OpenAI-kompatibilis API, például Open WebUI. A módosítások mentés után az új fordításoknál lépnek életbe.')
        settings_description.setObjectName('small')
        settings_description.setWordWrap(True)
        settings_layout.addWidget(settings_description)

        def settings_field(caption, placeholder, value='', secret=False):
            field_label = QLabel(caption)
            field_label.setObjectName('section')
            settings_layout.addWidget(field_label)
            entry = QLineEdit()
            entry.setPlaceholderText(placeholder)
            entry.setText(value or '')
            entry.setClearButtonEnabled(not secret)
            if secret:
                entry.setEchoMode(QLineEdit.EchoMode.Password)
            settings_layout.addWidget(entry)
            return entry

        self.api_url_input = settings_field('API VÉGPONT', 'https://szerverem/api/chat/completions', cfg.get('api_url'))
        self.api_key_input = settings_field('API-KULCS', 'Opcionális, ha nincs szükség hitelesítésre', cfg.get('api_key'), True)
        reveal_row = QHBoxLayout()
        self.reveal_key = QCheckBox('API-kulcs megjelenítése')
        self.reveal_key.toggled.connect(lambda checked: self.api_key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        reveal_row.addWidget(self.reveal_key)
        reveal_row.addStretch()
        settings_layout.addLayout(reveal_row)
        def model_picker(caption, initial, optional=False):
            heading = QLabel(caption)
            heading.setObjectName('section')
            settings_layout.addWidget(heading)
            picker = QComboBox()
            picker.setEditable(True)
            picker.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            picker.setMinimumWidth(260)
            picker.setMaxVisibleItems(15)
            picker.lineEdit().setPlaceholderText('Válassz a listából, vagy írd be az azonosítót')
            if optional:
                picker.addItem('')
            picker.setEditText(initial or '')
            settings_layout.addWidget(picker)
            return picker

        self.model_input = model_picker('ELSŐDLEGES MODELL', cfg.get('model'))
        self.fallback_input = model_picker('TARTALÉK MODELL', cfg.get('fallback_model'), True)
        api_buttons = QHBoxLayout()
        self.test_api_button = self.btn('Kapcsolat tesztelése', lambda: self.start_model_request('test'))
        self.load_models_button = self.btn('Modellek lekérése', lambda: self.start_model_request('load'), role='primary')
        api_buttons.addWidget(self.test_api_button)
        api_buttons.addWidget(self.load_models_button)
        settings_layout.addLayout(api_buttons)
        self.api_test_status = QLabel('')
        self.api_test_status.setWordWrap(True)
        self.api_test_status.setTextFormat(Qt.TextFormat.PlainText)
        self.api_test_status.setContentsMargins(12, 9, 12, 9)
        self.api_test_status.hide()
        settings_layout.addWidget(self.api_test_status)
        self.discovery_worker = None
        self.discovery_task = None
        model_hint = QLabel('A teszt a modelllista API-t és a hitelesítést ellenőrzi, nem indít fizetős fordítást. A listában nem minden modell képes képeket értelmezni.')
        model_hint.setObjectName('small')
        model_hint.setWordWrap(True)
        settings_layout.addWidget(model_hint)
        security_info = QLabel('Az API-kulcs titkosítva, a Windows Hitelesítőadat-kezelőben tárolódik. A képernyőkép csak kifejezett fordításkéréskor kerül elküldésre. HTTPS ellenőrzés bekapcsolva.')
        security_info.setObjectName('small')
        security_info.setWordWrap(True)
        settings_layout.addWidget(security_info)
        shortcut_title = QLabel('GYORSBILLENTYŰK ÉS FPS MÓD')
        shortcut_title.setObjectName('section')
        settings_layout.addWidget(shortcut_title)
        shortcut_note = QLabel('Kattints a mezőre, és nyomd le a kívánt kombinációt vagy az oldalsó egérgombot. Esc: megszakítás · Backspace: kikapcsolás. A Mouse3/Mouse4/Mouse5 továbbra is eljut a játékhoz. A bezárás-parancs csak az ablakot vagy kijelölést zárja be.')
        shortcut_note.setObjectName('small')
        shortcut_note.setWordWrap(True)
        settings_layout.addWidget(shortcut_note)
        self.shortcut_inputs = {}
        for action, label in ACTION_NAMES.items():
            row = QHBoxLayout()
            label_widget = QLabel(label)
            label_widget.setMinimumWidth(180)
            row.addWidget(label_widget)
            picker = ShortcutRecorder()
            picker.setText(self.cfg.get('hotkeys', HOTKEY_DEFAULTS).get(action, ''))
            picker.capture_started.connect(self.shortcut_capture_started.emit)
            picker.capture_finished.connect(self.shortcut_capture_finished.emit)
            self.shortcut_inputs[action] = picker
            row.addWidget(picker, 1)
            settings_layout.addLayout(row)
        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel('FPS középső képkivágás: szélesség'))
        self.fps_width_input = QSpinBox()
        self.fps_width_input.setRange(15, 100)
        self.fps_width_input.setSuffix('%')
        fps_row.addWidget(self.fps_width_input)
        fps_row.addWidget(QLabel('magasság'))
        self.fps_height_input = QSpinBox()
        self.fps_height_input.setRange(15, 100)
        self.fps_height_input.setSuffix('%')
        fps_row.addWidget(self.fps_height_input)
        settings_layout.addLayout(fps_row)
        fps_note = QLabel('FPS módban a kijelölés helyett azonnal a képernyő középső részét fordítja. Nem kell mozgatnod az egérmutatót. A képrögzítés kizárólag kérésre történik.')
        fps_note.setObjectName('small')
        fps_note.setWordWrap(True)
        settings_layout.addWidget(fps_note)
        self.settings_status = QLabel('')
        self.settings_status.setObjectName('status')
        self.settings_status.setWordWrap(True)
        settings_layout.addWidget(self.settings_status)
        settings_actions = QHBoxLayout()
        settings_actions.addStretch()
        settings_actions.addWidget(self.btn('Mégse', self.close_settings))
        settings_actions.addWidget(self.btn('Beállítások mentése', self.save_settings, role='primary'))
        settings_layout.addLayout(settings_actions)
        settings_layout.addStretch()
        content.addWidget(self.settings_panel, 1)
        self.settings_panel.hide()

        self.history_panel = QFrame()
        self.history_panel.setObjectName('historyPanel')
        history_layout = QVBoxLayout(self.history_panel)
        history_layout.setContentsMargins(11, 10, 11, 10)
        history_layout.setSpacing(8)
        section_row = QHBoxLayout()
        section = QLabel('MENTETT FORDÍTÁSOK')
        section.setObjectName('section')
        section_row.addWidget(section)
        section_row.addStretch()
        self.count_label = QLabel('')
        self.count_label.setObjectName('small')
        section_row.addWidget(self.count_label)
        history_layout.addLayout(section_row)

        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText('Keresés címben, tartalomban vagy dátumban…')
        self.history_search.setClearButtonEnabled(True)
        self.history_search.textChanged.connect(self.refresh_history)
        history_layout.addWidget(self.history_search)

        folder_row = QHBoxLayout()
        self.folder_filter = QComboBox()
        self.folder_filter.setToolTip('Előzmények szűrése mappa szerint')
        self.folder_filter.currentIndexChanged.connect(self.refresh_history)
        folder_row.addWidget(self.folder_filter, 1)
        self.new_folder_button = self.btn('+ Mappa', lambda: self.begin_edit('new_folder'), 'Új mappa létrehozása')
        self.rename_folder_button = self.btn('Átnevez', lambda: self.begin_edit('rename_folder'), 'Kiválasztott mappa átnevezése')
        self.delete_folder_button = self.btn('Töröl', self.ask_delete_folder, 'Mappa törlése (fordítások megmaradnak)')
        for b in (self.new_folder_button, self.rename_folder_button, self.delete_folder_button):
            folder_row.addWidget(b)
        history_layout.addLayout(folder_row)

        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(110)
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_list.setToolTip('Dupla kattintás: megnyitás • F2: átnevezés')
        self.history_list.itemDoubleClicked.connect(self.select_history)
        self.history_list.currentItemChanged.connect(self.on_selection_change)
        history_layout.addWidget(self.history_list, 1)
        self.rename_shortcut = QShortcut(QKeySequence('F2'), self.history_list)
        self.rename_shortcut.activated.connect(lambda: self.begin_edit('rename_entry'))

        action_row = QHBoxLayout()
        self.open_entry_button = self.btn('Megnyitás', self.open_selected_history, 'Kijelölt fordítás megjelenítése', 'primary')
        self.rename_entry_button = self.btn('Átnevezés', lambda: self.begin_edit('rename_entry'), 'Mentett fordítás címének módosítása (F2)')
        self.delete_button = self.btn('Törlés', self.delete_selected_history, 'Kijelölt fordítás törlése', 'danger')
        for b in (self.open_entry_button, self.rename_entry_button, self.delete_button):
            action_row.addWidget(b)
        history_layout.addLayout(action_row)

        move_row = QHBoxLayout()
        folder_hint = QLabel('Áthelyezés:')
        folder_hint.setObjectName('small')
        move_row.addWidget(folder_hint)
        self.move_folder = QComboBox()
        move_row.addWidget(self.move_folder, 1)
        self.move_button = self.btn('Mappába', self.move_selected, 'Kijelölt fordítás áthelyezése')
        move_row.addWidget(self.move_button)
        history_layout.addLayout(move_row)

        self.edit_panel = QFrame()
        edit_layout = QVBoxLayout(self.edit_panel)
        edit_layout.setContentsMargins(0, 4, 0, 0)
        self.edit_label = QLabel('')
        self.edit_label.setObjectName('section')
        edit_layout.addWidget(self.edit_label)
        edit_row = QHBoxLayout()
        self.edit_input = QLineEdit()
        self.edit_input.setMaxLength(120)
        self.edit_input.returnPressed.connect(self.apply_edit)
        edit_row.addWidget(self.edit_input, 1)
        edit_row.addWidget(self.btn('Mentés', self.apply_edit, role='primary'))
        edit_row.addWidget(self.btn('Mégse', self.cancel_edit))
        edit_layout.addLayout(edit_row)
        history_layout.addWidget(self.edit_panel)
        self.edit_panel.hide()

        self.confirm_panel = QFrame()
        confirm_layout = QVBoxLayout(self.confirm_panel)
        confirm_layout.setContentsMargins(0, 2, 0, 0)
        self.confirm_label = QLabel('')
        self.confirm_label.setWordWrap(True)
        confirm_layout.addWidget(self.confirm_label)
        confirm_row = QHBoxLayout()
        confirm_row.addWidget(self.btn('Igen, törlés', self.confirm_delete, role='danger'))
        confirm_row.addWidget(self.btn('Mégse', self.cancel_delete))
        confirm_row.addStretch()
        confirm_layout.addLayout(confirm_row)
        history_layout.addWidget(self.confirm_panel)
        self.confirm_panel.hide()

        footer_row = QHBoxLayout()
        self.clear_button = self.btn('Összes előzmény törlése', self.clear_history, 'Minden fordítás törlése', 'danger')
        footer_row.addWidget(self.clear_button)
        footer_row.addStretch()
        history_layout.addLayout(footer_row)
        self.history_status = QLabel('')
        self.history_status.setObjectName('status')
        self.history_status.setWordWrap(True)
        history_layout.addWidget(self.history_status)
        self.history_status.hide()
        content.addWidget(self.history_panel, 2)
        self.history_panel.hide()

        bottom = QHBoxLayout()
        self.footer_hint = QLabel('Ablak átméretezése: jobb alsó sarok')
        self.footer_hint.setObjectName('small')
        bottom.addWidget(self.footer_hint)
        bottom.addStretch()
        grip = QSizeGrip(self)
        grip.setFixedSize(21, 21)
        grip.setToolTip('Húzd az átméretezéshez')
        bottom.addWidget(grip)
        content.addLayout(bottom)
        self.sync_folders()
        self.restore_geometry()
        self._restoring_geometry = False

    @staticmethod
    def btn(label, callback, tooltip='', role=''):
        b = QPushButton(label)
        if tooltip:
            b.setToolTip(tooltip)
        if role:
            b.setProperty('role', role)
        b.clicked.connect(callback)
        return b

    def toggle_settings(self):
        if self.settings_panel.isVisible():
            self.close_settings()
            return
        self.api_url_input.setText(self.cfg.get('api_url', ''))
        self.api_key_input.setText(self.cfg.get('api_key', ''))
        self.model_input.setEditText(self.cfg.get('model', ''))
        self.fallback_input.setEditText(self.cfg.get('fallback_model', ''))
        for action, picker in self.shortcut_inputs.items():
            picker.setText(self.cfg.get('hotkeys', HOTKEY_DEFAULTS).get(action, ''))
        self.fps_width_input.setValue(int(self.cfg.get('fps_width_percent', 55)))
        self.fps_height_input.setValue(int(self.cfg.get('fps_height_percent', 40)))
        self.settings_status.clear()
        self.api_test_status.hide()
        self._history_before_settings = not self.history_panel.isHidden()
        if self._history_before_settings:
            self._history_size = self.size()
        else:
            self._compact_size = self.size()
        self._mode_switching = True
        self.history_panel.hide()
        self.label.hide()
        self.subtitle.hide()
        self.settings_panel.show()
        self.update_history_button()
        self.settings_button.setProperty('role', 'topActive')
        self.settings_button.style().unpolish(self.settings_button)
        self.settings_button.style().polish(self.settings_button)
        self.resize(self._settings_size)
        self._mode_switching = False
        self.api_url_input.setFocus()
        self.show()
        self.raise_()

    def close_settings(self):
        if self.settings_panel.isHidden():
            return
        self._settings_size = self.size()
        self._mode_switching = True
        self.settings_panel.hide()
        self.label.show()
        self.subtitle.show()
        if self._history_before_settings:
            self.history_panel.show()
            self.resize(self._history_size)
        else:
            self.resize(self._compact_size)
        self._mode_switching = False
        self.geometry_timer.start()
        self.update_history_button()
        self.settings_button.setProperty('role', 'top')
        self.settings_button.style().unpolish(self.settings_button)
        self.settings_button.style().polish(self.settings_button)

    def set_api_test_status(self, message, state='working'):
        palette = {
            'working': ('#17324d', '#5a9ed2', '#e4f2ff'),
            'success': ('#153b2e', '#43b88a', '#e2fff1'),
            'error': ('#48232b', '#dc6c7b', '#ffe6ea'),
        }
        background, border, foreground = palette[state]
        self.api_test_status.setStyleSheet(
            f'QLabel {{ background: {background}; color: {foreground}; '
            f'border: 1px solid {border}; border-radius: 9px; font-weight: 600; }}')
        self.api_test_status.setText(message)
        self.api_test_status.show()

    def show_active_model(self, model, fallback):
        role = 'TARTALÉK AI' if fallback else 'ELSŐDLEGES AI'
        self.subtitle.setText(f'FORDÍTÁS FOLYAMATBAN  •  {role}: {model}')
        self.subtitle.setToolTip(model)

    def start_model_request(self, action):
        if self.discovery_worker is not None and self.discovery_worker.isRunning():
            return
        try:
            url = validate_api_url(self.api_url_input.text().strip())
        except ValueError as exc:
            self.set_api_test_status('✕ ' + str(exc), 'error')
            return
        self.discovery_task = action
        self.test_api_button.setEnabled(False)
        self.load_models_button.setEnabled(False)
        self.set_api_test_status('◌ Kapcsolódás az API-hoz…', 'working')
        worker = ModelDiscovery(url, self.api_key_input.text())
        self.discovery_worker = worker
        worker.result.connect(self.on_discovery_result)
        worker.finished.connect(self.model_request_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def model_request_finished(self):
        self.discovery_worker = None

    def on_discovery_result(self, result):
        self.test_api_button.setEnabled(True)
        self.load_models_button.setEnabled(True)
        if not result.get('ok'):
            self.set_api_test_status('✕ Sikertelen kapcsolat: ' + result.get('error', 'Ismeretlen hiba.'), 'error')
            return
        models = result['models']
        if self.discovery_task == 'test':
            self.set_api_test_status(
                f'✓ Sikeres API-kapcsolat · {len(models)} elérhető modell. '
                'A fordítási képességet ez még nem ellenőrzi.', 'success')
            return
        for picker in (self.model_input, self.fallback_input):
            previous = picker.currentText()
            picker.blockSignals(True)
            picker.clear()
            picker.addItem('')
            picker.addItems(models)
            picker.setEditText(previous)
            picker.blockSignals(False)
        self.set_api_test_status(
            f'✓ {len(models)} modell betöltve. Válaszd ki a kívánt modellt, majd mentsd a beállításokat.', 'success')

    shortcuts_changed = Signal()
    shortcut_capture_started = Signal()
    shortcut_capture_finished = Signal()

    def save_settings(self):
        for field in self.shortcut_inputs.values():
            if field.recording:
                field.stop_recording()
        url = self.api_url_input.text().strip()
        model = self.model_input.currentText().strip()
        fallback = self.fallback_input.currentText().strip()
        try:
            url = validate_api_url(url)
        except ValueError as exc:
            self.settings_status.setText(str(exc))
            return
        if not model:
            self.settings_status.setText('Add meg az elsődleges modellt.')
            return
        try:
            shortcuts = normalize_hotkeys({name: field.text() for name, field in self.shortcut_inputs.items()})
        except ValueError as exc:
            self.settings_status.setText(str(exc))
            return
        updated = dict(self.cfg)
        updated.update(api_url=url, api_key=self.api_key_input.text().strip(),
                       model=model, fallback_model=fallback, hotkeys=shortcuts,
                       fps_width_percent=self.fps_width_input.value(),
                       fps_height_percent=self.fps_height_input.value())
        try:
            # Persist to the vault FIRST; leave existing configuration untouched on error.
            save_api_key(updated['api_key'])
            write_config(updated)
        except Exception:
            self.settings_status.setText('Nem sikerült menteni a Windows Hitelesítőadat-kezelőbe.')
            logging.exception('API key storage failed')
            return
        self.cfg.clear()
        self.cfg.update(updated)
        self.close_settings()
        self.subtitle.setText('Beállítások elmentve • Az új gyorsbillentyűk aktívak')
        self.shortcuts_changed.emit()

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self._restoring_geometry:
            self.geometry_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._restoring_geometry:
            if not self._mode_switching:
                if not self.settings_panel.isHidden():
                    self._settings_size = self.size()
                elif not self.history_panel.isHidden():
                    self._history_size = self.size()
                else:
                    self._compact_size = self.size()
            self.geometry_timer.start()

    def closeEvent(self, event):
        self.save_geometry()
        super().closeEvent(event)

    def save_geometry(self):
        if self._restoring_geometry:
            return
        try:
            data = {'x': self.x(), 'y': self.y(), 'width': self.width(), 'height': self.height(),
                    'history_open': self._history_preference,
                    'compact_width': self._compact_size.width(),
                    'compact_height': self._compact_size.height(),
                    'history_width': self._history_size.width(),
                    'history_height': self._history_size.height(),
                    'settings_width': self._settings_size.width(),
                    'settings_height': self._settings_size.height(),
                    'history_search': self.history_search.text(),
                    'history_folder': self.selected_folder()}
            tmp = self.WINDOW_PATH.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
            tmp.replace(self.WINDOW_PATH)
        except OSError as exc:
            logging.warning('Ablakhelyzet mentési hiba: %s', type(exc).__name__)

    def restore_geometry(self):
        try:
            data = json.loads(self.WINDOW_PATH.read_text(encoding='utf-8')) if self.WINDOW_PATH.exists() else {}
            w = max(465, min(1400, int(data.get('width', 660))))
            h = max(250, min(1100, int(data.get('height', 370))))
            screens = QApplication.screens()
            x, y = data.get('x'), data.get('y')
            if x is None or y is None:
                area = QApplication.primaryScreen().availableGeometry()
                x = area.x() + (area.width() - w) // 2
                y = area.y() + 45
            x, y = int(x), int(y)
            # A visible header must remain on a connected display, even after monitor changes.
            if not any(s.availableGeometry().adjusted(-40, -40, 40, 40).contains(QPoint(x + 70, y + 35)) for s in screens):
                area = QApplication.primaryScreen().availableGeometry()
                x, y = area.x() + 35, area.y() + 45
            self._compact_size = QSize(
                max(465, min(1400, int(data.get('compact_width', w)))),
                max(250, min(1100, int(data.get('compact_height', min(h, 370))))))
            self._history_size = QSize(
                max(465, min(1400, int(data.get('history_width', w)))),
                max(250, min(1100, int(data.get('history_height', max(h, 680))))))
            self._settings_size = QSize(
                max(465, min(1400, int(data.get('settings_width', w)))),
                max(250, min(1100, int(data.get('settings_height', 680)))))
            self.setGeometry(x, y, w, h)
            self.history_search.setText(str(data.get('history_search', '')))
            folder = data.get('history_folder', '')
            self.sync_folders(folder if isinstance(folder, str) else '')
            self._history_preference = data.get('history_open', False) is True
            if self._history_preference:
                self.refresh_history()
                self.history_panel.show()
                self.resize(self._history_size)
            else:
                self.history_panel.hide()
                self.resize(self._compact_size)
            self.update_history_button()
        except (ValueError, TypeError, OSError) as exc:
            logging.warning('Ablakhelyzet visszaállítási hiba: %s', type(exc).__name__)
            self.resize(660, 370)

    def selected_index(self):
        item = self.history_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def selected_folder(self):
        return self.folder_filter.currentData() or ''

    def sync_folders(self, selected=None):
        if selected is None and hasattr(self, 'folder_filter'):
            selected = self.selected_folder()
        self.folder_filter.blockSignals(True)
        self.folder_filter.clear()
        self.folder_filter.addItem('Összes mappa', '')
        self.folder_filter.addItem('Rendezetlen', '__unsorted__')
        for name in self.history.folders:
            self.folder_filter.addItem(name, name)
        i = self.folder_filter.findData(selected)
        self.folder_filter.setCurrentIndex(max(0, i))
        self.folder_filter.blockSignals(False)
        self.move_folder.clear()
        self.move_folder.addItem('Rendezetlen', '')
        for name in self.history.folders:
            self.move_folder.addItem(name, name)
        self.refresh_history()

    def on_selection_change(self, *_):
        index = self.selected_index()
        valid = index is not None and 0 <= index < len(self.history.items)
        for attr in ('delete_button', 'move_button', 'rename_entry_button', 'open_entry_button'):
            getattr(self, attr).setEnabled(valid)
        if valid:
            folder = self.history.items[index].get('folder', '')
            self.move_folder.setCurrentIndex(max(0, self.move_folder.findData(folder)))
        folder = self.selected_folder()
        self.rename_folder_button.setEnabled(folder in self.history.folders)
        self.delete_folder_button.setEnabled(folder in self.history.folders)

    def begin_edit(self, action):
        index = self.selected_index()
        folder = self.selected_folder()
        if action == 'rename_entry' and index is None:
            self.history_notice('Először válassz ki egy mentett fordítást.')
            return
        if action == 'rename_folder' and folder not in self.history.folders:
            self.history_notice('Válassz egy mappát az átnevezéshez.')
            return
        self.cancel_delete()
        self.edit_action = action
        self.edit_index = index
        self.edit_folder = folder
        self.edit_label.setText({
            'new_folder': 'ÚJ MAPPA', 'rename_folder': 'MAPPA ÁTNEVEZÉSE',
            'rename_entry': 'MENTETT FORDÍTÁS ÁTNEVEZÉSE'}[action])
        old = (self.history.items[index].get('title') or
               self.history.items[index]['text'].splitlines()[0][:80]) if action == 'rename_entry' else (folder if action == 'rename_folder' else '')
        self.edit_input.setText(old)
        self.edit_panel.show()
        self.edit_input.setFocus()
        self.edit_input.selectAll()

    def cancel_edit(self):
        self.edit_panel.hide()
        self.edit_action = None
        self.edit_index = None
        self.edit_folder = None

    def apply_edit(self):
        value = self.edit_input.text().strip()
        action = self.edit_action
        if not value:
            self.history_notice('Adj meg egy nevet.')
            return
        if action == 'new_folder':
            ok = self.history.create_folder(value)
            if ok:
                self.sync_folders(value)
        elif action == 'rename_folder':
            ok = self.history.rename_folder(self.edit_folder, value)
            if ok:
                self.sync_folders(value)
        elif action == 'rename_entry':
            index = self.edit_index
            ok = index is not None and self.history.update_item(index, title=value)
            if ok and index == self.history_index:
                self.display_history_item(index, show_window=False)
        else:
            return
        if ok:
            self.cancel_edit()
            self.refresh_history()
            self.history_notice('Sikeresen mentve.')
        else:
            self.history_notice('Nem sikerült menteni; ellenőrizd a nevet vagy a fájlhozzáférést.')

    def move_selected(self):
        index = self.selected_index()
        if index is None:
            return
        folder = self.move_folder.currentData() or ''
        if self.history.update_item(index, folder=folder):
            self.refresh_history()
            self.history_notice('Fordítás áthelyezve.')
        else:
            self.history_notice('Mentési hiba.')

    def ask_delete_folder(self):
        folder = self.selected_folder()
        if folder in self.history.folders:
            self.ask_delete('folder', folder)

    def eventFilter(self, watched, event):
        if watched is self.handle:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.drag_start = event.globalPosition().toPoint() - self.pos()
                return True
            if event.type() == QEvent.Type.MouseMove and self.drag_start is not None:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    self.move(event.globalPosition().toPoint() - self.drag_start)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self.drag_start = None
                return True
        return super().eventFilter(watched, event)

    def navigate(self, step):
        if not self.history.items:
            return
        index = self.history_index
        if index is None:
            index = len(self.history.items) - 1
        index = max(0, min(len(self.history.items) - 1, index + step))
        self.show_history_item(index)

    def display_history_item(self, index, show_window=True):
        if self.settings_panel.isVisible():
            self.close_settings()
        if 0 <= index < len(self.history.items):
            self.history_index = index
            entry = self.history.items[index]
            title = entry.get('title', '').strip()
            if title:
                self.subtitle.setText(f'{title}  •  {entry.get("time", "")}')
            else:
                self.subtitle.setText(f'MAGYAR FORDÍTÁS  •  {entry.get("time", "")}')
            self.label.setPlainText(entry['text'])
            if show_window:
                self.show()
                self.raise_()

    def show_history_item(self, index):
        self.display_history_item(index)

    @staticmethod
    def history_tooltip(value):
        text = value.strip()
        shortened = len(text) > 1200
        text = text[:1200]
        paragraphs = []
        for paragraph in text.splitlines():
            if not paragraph.strip():
                paragraphs.append('')
                continue
            paragraphs.extend(textwrap.wrap(paragraph, width=72,
                                            break_long_words=True,
                                            break_on_hyphens=False) or [''])
        body = '<br>'.join(html.escape(line) for line in paragraphs)
        suffix = '<br><br><i>Dupla kattintás: teljes szöveg megnyitása</i>' if shortened else ''
        return f'<div style="max-width: 480px; white-space: normal;">{body}{suffix}</div>'

    def refresh_history(self, *_):
        previous = self.selected_index()
        self.history_list.blockSignals(True)
        self.history_list.clear()
        term = self.history_search.text().casefold()
        folder_filter = self.selected_folder()
        count = 0
        for idx in range(len(self.history.items) - 1, -1, -1):
            entry = self.history.items[idx]
            folder = entry.get('folder', '')
            if folder_filter == '__unsorted__' and folder:
                continue
            if folder_filter not in ('', '__unsorted__') and folder != folder_filter:
                continue
            title = entry.get('title') or entry['text'].replace('\n', ' ')[:100]
            if term and not any(term in str(s).casefold() for s in (entry['text'], entry.get('time', ''), title, folder)):
                continue
            item = QListWidgetItem(f'{title[:110]}\n{entry.get("time", "")}  •  {folder or "Rendezetlen"}')
            item.setData(Qt.ItemDataRole.UserRole, idx)
            item.setToolTip(self.history_tooltip(entry['text']))
            self.history_list.addItem(item)
            count += 1
            if idx == previous:
                self.history_list.setCurrentItem(item)
        self.history_list.blockSignals(False)
        self.count_label.setText(f'{count} / {len(self.history.items)}')
        self.clear_button.setEnabled(bool(self.history.items))
        self.on_selection_change()

    def history_notice(self, message):
        self.history_status.setText(message)
        self.history_status.show()

    def ask_delete(self, kind, index=None):
        self.history_status.hide()
        self.cancel_edit()
        self.pending_delete = (kind, index)
        if kind == 'folder':
            self.confirm_label.setText(f'Törlöd a(z) „{index}” mappát? A fordításai a Rendezetlen csoportba kerülnek.')
        elif kind == 'one':
            self.confirm_label.setText('Végleg törlöd a kijelölt fordítást?')
        else:
            self.confirm_label.setText(f'Végleg törlöd mind a(z) {len(self.history.items)} fordítást?')
        self.confirm_panel.show()

    def cancel_delete(self):
        self.pending_delete = None
        self.confirm_panel.hide()

    def delete_selected_history(self):
        index = self.selected_index()
        if index is not None and 0 <= index < len(self.history.items):
            self.ask_delete('one', index)
        else:
            self.history_notice('Először válassz ki egy fordítást.')

    def clear_history(self):
        if self.history.items:
            self.ask_delete('all')

    def confirm_delete(self):
        pending = self.pending_delete
        self.cancel_delete()
        if pending is None:
            return
        kind, index = pending
        if kind == 'folder':
            if not self.history.delete_folder(index):
                self.history_notice('Nem sikerült törölni a mappát.')
                return
            self.sync_folders('')
            self.history_notice('A mappa törölve, a fordítások megmaradtak.')
        elif kind == 'one':
            if index is None or not 0 <= index < len(self.history.items):
                self.history_notice('A fordítás már nem található.')
                return
            if not self.history.delete(index):
                self.history_notice('Mentési hiba: a fordítás nem törölhető.')
                return
            if self.history_index == index:
                self.history_index = None
                self.label.setPlainText('A megjelenített fordítást törölted az előzményekből.')
            elif self.history_index is not None and self.history_index > index:
                self.history_index -= 1
            self.history_notice('Fordítás törölve.')
        elif kind == 'all':
            if not self.history.clear():
                self.history_notice('Mentési hiba: az előzmények nem törölhetők.')
                return
            self.history_index = None
            self.label.setPlainText('Az előzményeket törölted.')
            self.history_notice('Összes előzmény törölve.')
        self.refresh_history()

    def open_selected_history(self):
        index = self.selected_index()
        if index is not None:
            self.show_history_item(index)
            self.set_history_open(False)

    def select_history(self, item):
        self.show_history_item(item.data(Qt.ItemDataRole.UserRole))
        self.set_history_open(False)

    def update_history_button(self):
        active = not self.history_panel.isHidden() and self.settings_panel.isHidden()
        self.history_button.setProperty('role', 'topActive' if active else 'top')
        self.history_button.style().unpolish(self.history_button)
        self.history_button.style().polish(self.history_button)
        self.history_button.setToolTip(
            'Előzmények bezárása' if active else 'Előzmények megnyitása (Ctrl+Shift+H)')

    def set_history_open(self, should_open, focus=False, remember=True):
        # The compact translation view and the history view have independent sizes.
        # Expanding history must not permanently grow the translation window.
        was_open = not self.history_panel.isHidden()
        # Only explicit UI choices change the persisted history preference.
        if remember:
            self._history_preference = bool(should_open)
        if should_open == was_open:
            if should_open and focus:
                self.history_search.setFocus()
            self.update_history_button()
            if remember:
                self.geometry_timer.start()
            return
        self._mode_switching = True
        try:
            if should_open:
                self._compact_size = self.size()
                self.refresh_history()
                self.history_panel.show()
                self.resize(self._history_size)
                if focus:
                    self.history_search.setFocus()
            else:
                self._history_size = self.size()
                self.cancel_delete()
                self.cancel_edit()
                self.history_panel.hide()
                self.resize(self._compact_size)
        finally:
            self._mode_switching = False
        self.update_history_button()
        self.geometry_timer.start()

    def open_history(self):
        if not self.settings_panel.isHidden():
            self._history_before_settings = True
            self.close_settings()
            self.set_history_open(True, focus=True)
            return
        self.set_history_open(self.history_panel.isHidden(), focus=True)


    def show_history_from_hotkey(self):
        # Restore the user's last explicit history choice. Merely opening the
        # window must never turn a collapsed history panel back on.
        preferred = self._history_preference
        if not self.settings_panel.isHidden():
            self._history_before_settings = preferred
            self.close_settings()
        if not self.label.toPlainText().strip():
            self.label.setPlainText('Válassz egy korábbi fordítást az alábbi listából.')
        self.set_history_open(preferred, focus=preferred, remember=False)
        self.show()
        self.raise_()
        self.activateWindow()

    def prepare_translation(self):
        # Translation requests must not open or retain the history panel.
        self._history_before_settings = False
        if not self.settings_panel.isHidden():
            self.close_settings()
        self.set_history_open(False, remember=False)

    def show_message(self, text):
        if self.settings_panel.isVisible():
            self.close_settings()
        self.subtitle.setText('MAGYAR FORDÍTÁS   •   Kijelölés vagy FPS-gyorsfordítás')
        self.label.setPlainText(text)
        self.show()
        self.raise_()

class RegionSelector(QWidget):
    selected = Signal(object)

    def __init__(self):
        super().__init__()
        self.origin = None
        self.current = None
        self.image = None
        self.screen_rect = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def begin(self):
        # A képet még a kijelölőréteg megjelenése előtt rögzítjük.
        screen = QApplication.primaryScreen()
        self.screen_rect = screen.geometry()
        with mss.MSS() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
            self.image = Image.frombytes('RGB', shot.size, shot.rgb)
        self.origin = None
        self.current = None
        self.setGeometry(self.screen_rect)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 85))
        if self.origin is not None and self.current is not None:
            r = QRect(self.origin, self.current).normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(r, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor('#42c8ff'), 3))
            painter.drawRect(r)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.current = self.origin
            self.update()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.origin is None:
            return
        self.current = event.position().toPoint()
        r = QRect(self.origin, self.current).normalized().intersected(self.rect())
        self.hide()
        if r.width() < 12 or r.height() < 12:
            self.image = None
            return
        # Qt logikai koordinátáit a rögzített kép pixeleire alakítjuk.
        sx = self.image.width / self.width()
        sy = self.image.height / self.height()
        crop = self.image.crop((round(r.left()*sx), round(r.top()*sy),
                                round((r.left()+r.width())*sx), round((r.top()+r.height())*sy)))
        self.image = None  # Ne tartsuk memóriában a teljes képernyőt.
        self.selected.emit(crop)

    def cancel(self):
        """Dismiss the selection and discard the captured frame, without translating."""
        self.hide()
        self.origin = None
        self.current = None
        self.image = None
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            event.accept()
        else:
            super().keyPressEvent(event)


class Hotkeys(QObject):
    translate_requested = Signal()
    center_requested = Signal()
    history_requested = Signal()
    quit_requested = Signal()

    def __init__(self, bindings):
        super().__init__()
        self.bindings = normalize_hotkeys(bindings)
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self.ready = threading.Event()
        self.error = None
        self.thread_id = None
        self._callback = None
        self.thread = threading.Thread(target=self.listen, daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError('A gyorsbillentyűfigyelő nem indult el.')
        if self.error:
            raise RuntimeError(self.error)

    def _emit(self, action):
        {'select': self.translate_requested, 'center': self.center_requested,
         'history': self.history_requested, 'quit': self.quit_requested}[action].emit()

    def listen(self):
        self.thread_id = self.kernel32.GetCurrentThreadId()
        registered = []
        mouse_actions = {}
        hook = None
        try:
            for key_id, (action, value) in enumerate(self.bindings.items(), start=1):
                _, spec = parse_hotkey(value)
                if not spec:
                    continue
                if spec[0] == 'key':
                    if not self.user32.RegisterHotKey(None, key_id, spec[1] | 0x4000, spec[2]):
                        raise RuntimeError(f'A gyorsbillentyű foglalt: {value}')
                    registered.append(key_id)
                else:
                    mouse_actions[(spec[1], spec[2])] = action
            if mouse_actions:
                # Low-level global hook; read-only, never blocks a mouse action.
                class MSLLHOOKSTRUCT(ctypes.Structure):
                    _fields_ = [('pt', ctypes.wintypes.POINT), ('mouseData', ctypes.wintypes.DWORD),
                                ('flags', ctypes.wintypes.DWORD),
                                ('time', ctypes.wintypes.DWORD),
                                ('dwExtraInfo', ctypes.c_size_t)]
                CALLBACK = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                                               ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
                self.user32.CallNextHookEx.restype = ctypes.c_ssize_t
                self.user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                        ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
                self.user32.SetWindowsHookExW.restype = ctypes.c_void_p
                self.user32.SetWindowsHookExW.argtypes = [ctypes.c_int, CALLBACK,
                                                           ctypes.c_void_p, ctypes.wintypes.DWORD]
                self.user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

                def current_mods():
                    mods = 0
                    for vk, flag in [(0x11, 2), (0x12, 1), (0x10, 4), (0x5B, 8), (0x5C, 8)]:
                        if self.user32.GetAsyncKeyState(vk) & 0x8000:
                            mods |= flag
                    return mods

                def hook_proc(n, wparam, lparam):
                    if n >= 0 and wparam in (0x0207, 0x020B):  # WM_MBUTTONDOWN / WM_XBUTTONDOWN
                        event = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        if not (event.flags & 0x00000001):  # Ignore synthetic input
                            button = 0 if wparam == 0x0207 else (event.mouseData >> 16) & 0xFFFF
                            action = mouse_actions.get((current_mods(), button))
                            if action:
                                self._emit(action)
                    return self.user32.CallNextHookEx(None, n, wparam, lparam)
                self._callback = CALLBACK(hook_proc)
                hook = self.user32.SetWindowsHookExW(14, self._callback, None, 0)
                if not hook:
                    raise RuntimeError('Az egérgombokat nem sikerült figyelni (Windows hook).')
            self.ready.set()
            msg = ctypes.wintypes.MSG()
            action_ids = {i: action for i, action in enumerate(self.bindings, start=1)}
            while self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:  # WM_HOTKEY
                    action = action_ids.get(msg.wParam)
                    if action:
                        self._emit(action)
        except Exception as exc:
            self.error = str(exc)
            logging.exception('Windows hotkey or mouse hook failed')
            self.ready.set()
        finally:
            if hook:
                self.user32.UnhookWindowsHookEx(hook)
            for key_id in registered:
                self.user32.UnregisterHotKey(None, key_id)
            self._callback = None

    def close(self):
        if self.thread_id:
            self.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)  # WM_QUIT
        if self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=2.0)


# Per-user startup entry: no administrator privileges required.
STARTUP_REGISTRY_NAME = 'AIJatekasszisztens'


def portable_executable():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve()
    return None


def startup_registered():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            value, _ = winreg.QueryValueEx(key, STARTUP_REGISTRY_NAME)
        executable = portable_executable()
        return bool(executable and value == '"' + str(executable) + '"')
    except (FileNotFoundError, OSError):
        return False


def set_startup(enabled):
    import winreg
    executable = portable_executable()
    if enabled and executable is None:
        raise RuntimeError('Az automatikus indítás a lefordított EXE-verzióban érhető el.')
    path = r'Software\Microsoft\Windows\CurrentVersion\Run'
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                            winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, STARTUP_REGISTRY_NAME, 0,
                              winreg.REG_SZ, '"' + str(executable) + '"')
        else:
            try:
                winreg.DeleteValue(key, STARTUP_REGISTRY_NAME)
            except FileNotFoundError:
                pass


def main():
    if os.name != 'nt':
        raise SystemExit('Ez az alkalmazás Windowsra készült.')

    logging.basicConfig(filename=str(APP_DIR / 'hiba.log'), level=logging.WARNING,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
    migrate_previous_install()
    cfg = load_config()
    app = QApplication(sys.argv)
    app.setApplicationName('AI Játékasszisztens')
    app.setQuitOnLastWindowClosed(False)
    if icon_path().exists():
        app.setWindowIcon(QIcon(str(icon_path())))

    # Ugyanaz a felhasználó ne indíthasson két példányt, mert a hotkeyek ütköznének.
    singleton = QLockFile(str(APP_DIR / 'application.lock'))
    singleton.setStaleLockTime(0)
    if not singleton.tryLock(100):
        QMessageBox.information(None, 'AI Játékasszisztens',
                                'Az AI Játékasszisztens már fut az értesítési területen.\n'
                                'Előzmények és beállítások: tálcaikon jobb kattintás.')
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, 'AI Játékasszisztens',
                             'A Windows értesítési területe nem érhető el.')
        singleton.unlock()
        return 1

    history = HistoryStore()
    overlay = Overlay(cfg, history)
    selector = RegionSelector()
    active = {'worker': None, 'suppress_result': False}

    def send_selection(image):
        overlay.prepare_translation()
        if active['worker'] and active['worker'].isRunning():
            overlay.show_message('A fordítás még folyamatban van…')
            return
        max_width = max(320, int(cfg['max_image_width']))
        if image.width > max_width:
            image.thumbnail((max_width, max_width * image.height // image.width))
        active['suppress_result'] = False
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=88)
        overlay.show_message('Kijelölt terület fordítása folyamatban…')
        worker = Translator(buffer.getvalue(), cfg)
        active['worker'] = worker

        def handle_result(text):
            history.add(text)
            if active['suppress_result']:
                return  # The user closed the overlay while the API request was running.
            if history.items and history.items[-1]['text'] == text and not text.startswith('Fordítási hiba:'):
                overlay.show_history_item(len(history.items) - 1)
            else:
                overlay.show_message(text)

        worker.finished_text.connect(handle_result)
        worker.model_started.connect(overlay.show_active_model)
        worker.start()

    def translate():
        overlay.prepare_translation()
        if active['worker'] and active['worker'].isRunning():
            overlay.show_message('A fordítás még folyamatban van…')
            return
        overlay.hide()
        try:
            selector.begin()
        except Exception as exc:
            overlay.show_message(f'Kijelölési hiba: {exc}')
            logging.exception('Kijelölési hiba')

    def translate_center():
        overlay.prepare_translation()
        if active['worker'] and active['worker'].isRunning():
            overlay.show_message('A fordítás még folyamatban van…')
            return
        overlay.hide()
        # Allow the previous overlay to disappear before capturing the desktop.
        def capture_center():
            try:
                with mss.MSS() as sct:
                    shot = sct.grab(sct.monitors[1])
                image = Image.frombytes('RGB', shot.size, shot.rgb)
                w = max(15, min(100, int(cfg.get('fps_width_percent', 55)))) / 100.0
                h = max(15, min(100, int(cfg.get('fps_height_percent', 40)))) / 100.0
                crop_width = round(image.width * w)
                crop_height = round(image.height * h)
                left = (image.width - crop_width) // 2
                top = (image.height - crop_height) // 2
                crop = image.crop((left, top, left + crop_width, top + crop_height))
                image.close()
                send_selection(crop)
            except Exception as exc:
                overlay.show_message(f'FPS képrögzítési hiba: {exc}')
                logging.exception('Center capture failed')
        QTimer.singleShot(200, capture_center)

    def close_current_view():
        """Close only the current UI, never terminate the background tray process."""
        if selector.isVisible():
            selector.cancel()
            return
        if overlay.isVisible():
            active['suppress_result'] = True
            overlay.save_geometry()
            overlay.hide()
        # With neither window open, the hotkey deliberately does nothing.

    def open_settings():
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        if overlay.settings_panel.isHidden():
            overlay.toggle_settings()

    selector.selected.connect(send_selection)
    tray = QSystemTrayIcon(QIcon(str(icon_path())) if icon_path().exists()
                           else app.style().standardIcon(app.style().StandardPixmap.SP_ComputerIcon), app)
    tray.setToolTip('AI Játékasszisztens')
    menu = QMenu()
    action_translate = menu.addAction('Terület kijelölése')
    action_center = menu.addAction('FPS: középső terület fordítása')
    action_history = menu.addAction('Előzmények')
    action_settings = menu.addAction('Beállítások')
    menu.addSeparator()
    action_startup = menu.addAction('Automatikus indítás Windowszal')
    action_startup.setCheckable(True)
    action_startup.setChecked(startup_registered())
    menu.addSeparator()
    action_quit = menu.addAction('Kilépés')
    action_translate.triggered.connect(translate)
    action_center.triggered.connect(translate_center)
    action_history.triggered.connect(overlay.show_history_from_hotkey)
    action_settings.triggered.connect(open_settings)

    def toggle_startup(checked):
        try:
            set_startup(checked)
            action_startup.setChecked(startup_registered())
        except Exception as exc:
            action_startup.setChecked(startup_registered())
            logging.exception('Automatic startup setting failed')
            tray.showMessage('Automatikus indítás', str(exc),
                             QSystemTrayIcon.MessageIcon.Warning, 5000)

    action_startup.triggered.connect(toggle_startup)
    menu.aboutToShow.connect(lambda: action_startup.setChecked(startup_registered()))
    tray.setContextMenu(menu)

    def tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            overlay.show_history_from_hotkey()

    tray.activated.connect(tray_activated)
    tray.show()

    current_hotkeys = {'obj': None}

    def bind_hotkeys():
        previous = current_hotkeys['obj']
        if previous:
            previous.close()
            current_hotkeys['obj'] = None
        try:
            instance = Hotkeys(cfg.get('hotkeys'))
            instance.translate_requested.connect(translate)
            instance.center_requested.connect(translate_center)
            instance.history_requested.connect(overlay.show_history_from_hotkey)
            instance.quit_requested.connect(close_current_view)
            current_hotkeys['obj'] = instance
        except Exception as exc:
            logging.exception('Hotkey binding failed')
            tray.showMessage('AI Játékasszisztens', str(exc), QSystemTrayIcon.MessageIcon.Warning, 6000)
            overlay.settings_status.setText('Gyorsbillentyűhiba: ' + str(exc))

    def update_tray_labels():
        binds = cfg.get('hotkeys', {})
        action_translate.setText(f"Terület kijelölése    {binds.get('select', '')}")
        action_center.setText(f"FPS: középső terület    {binds.get('center', '')}")
        action_history.setText(f"Előzmények    {binds.get('history', '')}")

    def suspend_hotkeys_for_capture():
        previous = current_hotkeys['obj']
        if previous:
            previous.close()
            current_hotkeys['obj'] = None

    overlay.shortcut_capture_started.connect(suspend_hotkeys_for_capture)
    overlay.shortcut_capture_finished.connect(bind_hotkeys)
    overlay.shortcuts_changed.connect(bind_hotkeys)
    overlay.shortcuts_changed.connect(update_tray_labels)
    update_tray_labels()

    shutting_down = {'value': False}

    def shutdown():
        if shutting_down['value']:
            return
        shutting_down['value'] = True
        overlay.save_geometry()
        if current_hotkeys['obj'] is not None:
            current_hotkeys['obj'].close()
        worker = active['worker']
        if worker and worker.isRunning():
            # A még futó HTTP-kérés lezárulta után lépünk ki, különben a QThread megsérülhet.
            worker.finished.connect(app.quit)
            overlay.hide()
            tray.showMessage('AI Játékasszisztens', 'Kilépés a folyamatban lévő fordítás után.',
                             QSystemTrayIcon.MessageIcon.Information, 3000)
            return
        app.quit()

    action_quit.triggered.connect(shutdown)
    bind_hotkeys()

    # A program induláskor kizárólag a tálcán jelenik meg, nem nyit fordítóablakot.
    # Nem készül folyamatos képernyőkép. Csak kijelöléskor történik rögzítés.
    code = app.exec()
    tray.hide()
    singleton.unlock()
    return code


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        logging.exception('Váratlan indítási hiba')
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, 'AI Játékasszisztens – hiba',
                                 'Az alkalmazás hibába ütközött.\nNapló: ' + str(APP_DIR / 'hiba.log'))
        except Exception:
            pass
        sys.exit(1)
