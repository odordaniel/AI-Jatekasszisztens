"""Record-then-transcribe game audio translation for AI Játékasszisztens.

No live subtitle is shown. After recording stops, a normal interactive
transcript window displays speaker-attributed Hungarian translations.
"""
import asyncio
import collections
import queue
import tempfile
import html
import wave
import json
import logging
import os
import re
import threading
import traceback
import time
import requests
import certifi
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QThread, Signal, QPoint, QRect, QTimer
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit,
                              QPushButton, QComboBox, QMessageBox, QSpinBox,
                              QCheckBox, QFormLayout, QGroupBox, QApplication, QSizePolicy,
                              QTextBrowser)
import keyring

DEFAULT_URL = 'https://generativelanguage.googleapis.com'
DEFAULT_MODEL = 'gemini-3.5-transcribe'
VAULT_SERVICE = 'AIJatekasszisztens'
VAULT_ACCOUNT = 'live-translation-api-key'


def safe_api_url(value):
    url = value.strip().rstrip('/')
    p = urlsplit(url)
    if p.username or p.password or p.query or p.fragment or not p.hostname:
        raise ValueError('Érvénytelen API URL.')
    if p.scheme != 'https' and not (p.scheme == 'http' and p.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('Távoli szolgáltatásnál HTTPS szükséges.')
    return url


def genai_client(api_key, url):
    from google import genai
    from google.genai import types
    options = types.HttpOptions(api_version='v1beta')
    if url.rstrip('/').lower() != DEFAULT_URL:
        options = types.HttpOptions(api_version='v1beta', base_url=url)
    return genai.Client(api_key=api_key, http_options=options)


class Devices(QThread):
    loaded = Signal(list)
    failed = Signal(str)

    def run(self):
        try:
            import soundcard as sc  # Must remain outside Qt GUI thread (Windows COM).
            self.loaded.emit([(s.name, s.id) for s in sc.all_speakers()])
        except ImportError:
            self.failed.emit('Hiányzik a soundcard csomag. Telepítsd a requirements.txt függőségeit, vagy használd a teljes portable csomagot.')
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')


class Models(QThread):
    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, key, url):
        super().__init__()
        self.key, self.url = key, url

    def run(self):
        try:
            client = genai_client(self.key, self.url)
            try:
                models = [m.name.removeprefix('models/') for m in client.models.list() if getattr(m, 'name', None)]
                self.loaded.emit(sorted(set(models), key=lambda n: (not any(k in n.lower() for k in ('live', 'translate', 'audio')), n.lower())))
            finally:
                client.close()
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')


class TextModels(QThread):
    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, url, key):
        super().__init__()
        self.url, self.key = url, key

    def run(self):
        try:
            from urllib.parse import urlsplit
            parsed = urlsplit(self.url)
            if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
                raise ValueError('HTTPS szükséges.')
            base = self.url.strip().rstrip('/')
            if not base.endswith('/chat/completions'):
                raise ValueError('A fordító URL /chat/completions útvonallal végződjön.')
            endpoint = (base[:-len('/api/chat/completions')] + '/api/models'
                        if base.endswith('/api/chat/completions') else
                        base[:-len('/chat/completions')] + '/models')
            headers = {'Authorization': 'Bearer ' + self.key} if self.key else {}
            with requests.Session() as session:
                session.trust_env = False
                resp = session.get(endpoint, headers=headers, timeout=(8, 20), allow_redirects=False,
                                   verify=(str(Path.home() / 'AppData' / 'Local' / 'AIJatekasszisztens' / 'caddy-root.crt') if
                                           (urlsplit(endpoint).hostname or '').endswith('.home.arpa') and
                                           (Path.home() / 'AppData' / 'Local' / 'AIJatekasszisztens' / 'caddy-root.crt').is_file()
                                           else certifi.where()))
                resp.raise_for_status()
                data = resp.json()
            raw = data.get('data', data.get('models', []))
            names = [x if isinstance(x, str) else x.get('id', x.get('name', ''))
                     for x in raw if isinstance(x, (str, dict))]
            self.loaded.emit(sorted({x.removeprefix('models/') for x in names if x}))
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')


class LiveWorker(QThread):
    """Batch speech diarization with ongoing audio capture and ordered translation.

    Windows audio is captured in a dedicated thread. Whole audio excerpts are
    submitted to Gemini 3.5 Transcribe using the non-streaming Interactions API;
    completed speaker turns are then sent to the configured text translation API.
    """
    subtitle = Signal(str, str)
    status = Signal(str)
    failed = Signal(str)
    completed = Signal(list, str)
    recording_changed = Signal(bool)

    def __init__(self, key, url, model, device_id, recovery_path, translate_url,
                 translate_key, translate_model, fallback_model='',
                 silence_seconds=2.0, max_segment_seconds=35, game_hint=''):
        super().__init__()
        self.key, self.url, self.model, self.device_id = key, url, model, device_id
        self.translate_url, self.translate_key = translate_url, translate_key
        self.translate_model, self.fallback_model = translate_model, fallback_model
        self.recovery_path = recovery_path
        self.silence_seconds = max(0.6, min(4.0, float(silence_seconds)))
        self.max_segment_seconds = max(10, min(90, int(max_segment_seconds)))
        self.cancel = threading.Event()
        self.stop_requested = threading.Event()
        self.game_hint = game_hint.strip()
        self.inferred_game = ''
        self.detected_game = ''
        self.entries = []
        self.started = datetime.now().isoformat(timespec='seconds')
        self._previous = []
        self._fatal_error = ''
        self._sequence = 0

    def _checkpoint(self):
        if not self.entries:
            return
        payload = {'started': self.started, 'stt_model': self.model,
                   'translate_model': self.translate_model, 'entries': self.entries}
        tmp = self.recovery_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(self.recovery_path)

    def _translate_sync(self, source):
        from urllib.parse import urlsplit
        from pathlib import Path
        url = self.translate_url.strip()
        parsed = urlsplit(url)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
            raise ValueError('A fordító végpontja HTTPS legyen (kivéve localhost).')
        if not parsed.path.endswith('/chat/completions') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Érvénytelen fordító API URL: /chat/completions szükséges.')
        headers = {'Content-Type': 'application/json'}
        if self.translate_key:
            headers['Authorization'] = 'Bearer ' + self.translate_key
        context = '\n'.join(self._previous[-3:])
        game = self.game_hint or self.inferred_game
        prompt = (('A játék feltételezett címe (csak terminológiai segítség, ne állíts tényként): ' + game + '\n') if game else '') + ('Fordítsd magyarra az alábbi videojáték-párbeszédet. '
                  'Tartsd meg a neveket és a jelentést. Ne adj magyarázatot, '
                  'idézőjelet vagy bevezetőt. Csak a magyar fordítást írd.\n'
                  + ('Előző mondatok (csak kontextus):\n' + context + '\n' if context else '')
                  + 'Most fordítandó szöveg:\n' + source)
        models = [self.translate_model]
        if self.fallback_model and self.fallback_model not in models:
            models.append(self.fallback_model)
        ca_path = Path.home() / 'AppData' / 'Local' / 'AIJatekasszisztens' / 'caddy-root.crt'
        verify = str(ca_path) if parsed.hostname and parsed.hostname.endswith('.home.arpa') and ca_path.is_file() else certifi.where()
        errors = []
        with requests.Session() as client:
            client.trust_env = False
            for model in models:
                if not model:
                    continue
                try:
                    with client.post(url, json={'model': model, 'stream': False, 'messages': [
                        {'role': 'user', 'content': prompt}]}, headers=headers,
                        timeout=(8, 45), stream=True, allow_redirects=False,
                        verify=verify) as response:
                        if response.status_code >= 400:
                            raise RuntimeError(f'HTTP {response.status_code}: ' + response.text[:400])
                        chunks = []
                        total = 0
                        for part in response.iter_content(chunk_size=8192):
                            total += len(part)
                            if total > 256*1024:
                                raise RuntimeError('Túl nagy AI-válasz')
                            chunks.append(part)
                        data = json.loads(b''.join(chunks).decode('utf-8'))
                    text = data['choices'][0]['message']['content']
                    if isinstance(text, list):
                        text = ''.join(p.get('text', '') for p in text if isinstance(p, dict))
                    translated = str(text).strip()
                    if not translated:
                        raise RuntimeError('Üres fordítás')
                    return translated, model
                except Exception as exc:
                    errors.append(f'{model}: {type(exc).__name__}: {exc}')
        raise RuntimeError(' | '.join(errors))

    def _infer_context(self, turns):
        """Try to recognize ONLY the game, never character names or voice identities.

        The caller may already have an unambiguous installed-game folder. No
        transcript inference should override that. A vague genre/dialogue is
        not sufficient evidence for automatic history categorization.
        """
        if self.inferred_game or not turns or not self.translate_model:
            return
        fragments = []
        for _, source in turns:
            fragments.append(source)
            if sum(len(x) for x in fragments) > 6000:
                break
        excerpt = '\n'.join(fragments)
        if len(excerpt.strip()) < 150:
            return
        prompt = (
            'Az alábbi videojáték-párbeszédből csak akkor azonosíts játékot, '
            'ha több EGYEDI, KONKRÉT és összetartozó, a szövegben ténylegesen '
            'szereplő bizonyíték alapján gyakorlatilag kétségtelen az azonosság. '
            'Általános párbeszédből, zsánerből, kitalált karakternevekből NE '
            'következtess. Ha bizonytalan vagy, térj vissza üres névvel. '
            'Ne próbálj szereplőket megnevezni. Kizárólag JSON: '
            '{"game":"", "evidence":["idézet 1", "idézet 2"]}.\n' + excerpt
        )
        parsed = urlsplit(self.translate_url)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
            return
        ca = Path.home() / 'AppData' / 'Local' / 'AIJatekasszisztens' / 'caddy-root.crt'
        verify = str(ca) if (parsed.hostname or '').endswith('.home.arpa') and ca.is_file() else certifi.where()
        try:
            with requests.Session() as session:
                session.trust_env = False
                resp = session.post(self.translate_url, headers={'Content-Type':'application/json',
                    **({'Authorization':'Bearer '+self.translate_key} if self.translate_key else {})},
                    json={'model':self.translate_model,'stream':False,
                          'messages':[{'role':'user','content':prompt}]},
                    timeout=(8,50), verify=verify, allow_redirects=False)
                resp.raise_for_status()
                answer = resp.json()['choices'][0]['message']['content']
            if isinstance(answer,list):
                answer=''.join(x.get('text','') for x in answer if isinstance(x,dict))
            answer=str(answer).strip()
            if answer.startswith('```'):
                answer=re.sub(r'^```(?:json)?\s*|\s*```$', '', answer, flags=re.I)
            obj=json.loads(answer)
            if not isinstance(obj,dict):
                return
            game=str(obj.get('game') or '').strip()
            evidence=obj.get('evidence')
            # Require multiple independently present, concrete source clues.
            if not isinstance(evidence,list) or len(evidence)<2 or not game:
                return
            if any(not isinstance(clue,str) or len(clue.strip())<5 or clue.casefold() not in excerpt.casefold()
                   for clue in evidence[:2]):
                return
            game = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', game).strip(' .')
            if 3 <= len(game) <= 80:
                self.inferred_game = game
        except Exception:
            logging.info('A játék automatikus felismeréséhez kevés adat áll rendelkezésre.')

    def _save_entry(self, source, translation, used_model, error='', speaker='', elapsed=None):
        # Word-level offsets refer to the start of the recording, not translation time.
        elapsed = max(0.0, float(elapsed or 0.0))
        hours, rem = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(rem, 60)
        stamp = f'{hours:02d}:{minutes:02d}:{seconds:02d}'
        self.entries.append({'time': stamp, 'elapsed_seconds': round(elapsed, 2),
                             'original': source, 'magyar': translation,
                             'speaker': speaker, 'stt_model': self.model,
                             'translate_model': used_model, 'error': error})
        self._checkpoint()

    @staticmethod
    def _seconds(value):
        if value is None:
            return None
        if hasattr(value, 'total_seconds'):
            return float(value.total_seconds())
        if isinstance(value, (int, float)):
            return float(value)
        match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)s?\s*', str(value))
        return float(match.group(1)) if match else None

    @staticmethod
    def _speaker_turns(interaction):
        """Preserve speaker boundaries plus audio-relative word start offsets."""
        words = []
        for step in getattr(interaction, 'steps', None) or []:
            for content in getattr(step, 'content', None) or []:
                for word in getattr(content, 'annotations', None) or []:
                    if getattr(word, 'type', None) == 'word_info' and getattr(word, 'text', None):
                        offset = LiveWorker._seconds(getattr(word, 'start_offset', None))
                        words.append((str(getattr(word, 'speaker', '') or ''), str(word.text), offset))
        if not words:
            text = str(getattr(interaction, 'output_text', '') or '').strip()
            return [('', text, None)] if text else []
        turns = []
        speaker = None
        tokens = []
        first_offset = None
        for current, word, offset in words:
            if speaker is not None and current != speaker:
                turns.append((speaker, ' '.join(tokens).strip(), first_offset))
                tokens = []
                first_offset = None
            speaker = current
            if first_offset is None:
                first_offset = offset
            tokens.append(word)
        if tokens:
            turns.append((speaker or '', ' '.join(tokens).strip(), first_offset))
        return [(speaker, text, offset) for speaker, text, offset in turns if text]

    def _transcribe_chunk(self, client, samples, index):
        """Upload one WAV excerpt and request speaker diarization (not streaming)."""
        import numpy as np
        fd, wav_path = tempfile.mkstemp(prefix='ai-jatek-hang-', suffix='.wav')
        os.close(fd)
        remote = None
        try:
            with wave.open(wav_path, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(np.clip(samples * 32767, -32768, 32767).astype('<i2').tobytes())
            self.status.emit(f'{index}. hangszakasz feltöltése · beszélők felismerése…')
            remote = client.files.upload(file=wav_path)
            interaction = client.interactions.create(
                model=self.model,
                input=[{'type': 'audio', 'uri': remote.uri,
                        'mime_type': remote.mime_type or 'audio/wav'}],
                generation_config={'transcription_config': {
                    'mode': {'type': 'verbatim', 'diarization_mode': 'speaker', 'timestamp_granularities': ['word']}}},
            )
            return self._speaker_turns(interaction)
        finally:
            if remote is not None and getattr(remote, 'name', None):
                try:
                    client.files.delete(name=remote.name)
                except Exception:
                    logging.warning('Felhős ideiglenes hangfájl nem törölhető: %s', remote.name)
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    def run(self):
        """Record first; after explicit stop, transcribe and translate the recording."""
        import numpy as np
        sample_rate = 16000
        block_frames = 1600
        # Diarization requests support up to 30 minutes. Use 20-minute clips to
        # allow long sessions without loading the entire recording into memory.
        max_frames = sample_rate * 20 * 60
        paths = []
        client = None
        try:
            self.status.emit('Rögzítés folyamatban – leállításig csak hallgatok…')
            import soundcard as sc  # COM initialized outside the Qt GUI thread
            speaker = next((item for item in sc.all_speakers() if item.id == self.device_id), None)
            if speaker is None:
                raise RuntimeError('A kiválasztott hangkimenet nem található.')
            mic = sc.get_microphone(id=speaker.id, include_loopback=True)
            self.recording_changed.emit(True)
            with tempfile.TemporaryDirectory(prefix='ai-jatek-felvetel-') as folder:
                folder = Path(folder)
                part = 0
                frames_written = 0
                current = None
                try:
                    with mic.recorder(samplerate=sample_rate, channels=1, blocksize=block_frames) as recorder:
                        while not self.stop_requested.is_set() and not self.cancel.is_set():
                            if current is None or frames_written >= max_frames:
                                if current is not None:
                                    current.close()
                                part += 1
                                path = folder / f'felvetel-{part:03d}.wav'
                                paths.append(path)
                                current = wave.open(str(path), 'wb')
                                current.setnchannels(1)
                                current.setsampwidth(2)
                                current.setframerate(sample_rate)
                                frames_written = 0
                            samples = recorder.record(numframes=block_frames)
                            pcm = np.clip(np.asarray(samples[:,0],dtype=np.float32)*32767,
                                          -32768,32767).astype('<i2')
                            current.writeframes(pcm.tobytes())
                            frames_written += len(pcm)
                finally:
                    if current is not None:
                        current.close()
                if self.cancel.is_set():
                    self.status.emit('Rögzítés megszakítva.')
                    return
                if not paths:
                    self.status.emit('Nem készült hangfelvétel.')
                    return
                self.status.emit('Felvétel befejezve. Gemini átírás és beszélőfelismerés…')
                client = genai_client(self.key,self.url)
                all_turns=[]
                for i,path in enumerate(paths,1):
                    if self.cancel.is_set():
                        break
                    try:
                        self.status.emit(f'Átirat készítése: {i}/{len(paths)} hangrész…')
                        remote = None
                        try:
                            remote=client.files.upload(file=str(path))
                            interaction=client.interactions.create(
                                model=self.model,
                                input=[{'type':'audio','uri':remote.uri,
                                        'mime_type':remote.mime_type or 'audio/wav'}],
                                generation_config={'transcription_config':{'mode':{
                                    'type':'verbatim','diarization_mode':'speaker', 'timestamp_granularities':['word']}}})
                            turns=self._speaker_turns(interaction)
                            for spk,source,offset in turns:
                                # Speaker labels are clip-local; time offsets are clip-relative.
                                key=f'clip{i}:{spk or "unknown"}'
                                elapsed = (i-1)*20*60 + (offset or 0.0)
                                all_turns.append((key, source, elapsed))
                        finally:
                            if remote is not None and getattr(remote,'name',None):
                                try:
                                    client.files.delete(name=remote.name)
                                except Exception:
                                    logging.warning('A Gemini ideiglenes fájl törlése nem sikerült.')
                    except Exception as exc:
                        self.failed.emit(f'{i}. hangrész átírása sikertelen: {type(exc).__name__}: {exc}')
                if not all_turns:
                    self.status.emit('Nem találtam felismerhető beszédet a felvételen.')
                    return
                # Recognize a game title only when supported by specific evidence.
                first_clip=[(key.split(':',1)[1],source) for key,source,_ in all_turns
                            if key.startswith('clip1:')]
                self.status.emit('Játék automatikus felismerésének ellenőrzése…')
                self._infer_context(first_clip)
                count=len(all_turns)
                for i,(key,source,elapsed) in enumerate(all_turns,1):
                    if self.cancel.is_set():
                        break
                    if not source.strip():
                        continue
                    clip,spk=key.split(':',1)
                    number=spk.split('_')[-1] if spk.startswith('spk_') else '?'
                    name=f'Beszélő {number}' + (f' ({clip[4:]}. rész)' if clip!='clip1' else '')
                    self.status.emit(f'Fordítás {i}/{count} – {name}…')
                    try:
                        translated,used=self._translate_sync(source)
                        self._previous=(self._previous+[source])[-3:]
                        self._save_entry(source,translated,used,speaker=name,elapsed=elapsed)
                    except Exception as exc:
                        self.failed.emit(f'Fordítási hiba ({i}/{count}): {exc}')
                        self._save_entry(source,'',self.translate_model,
                                         error=str(exc),speaker=name,elapsed=elapsed)
                self.status.emit('A szövegkönyv elkészült.')
        except Exception as exc:
            self._fatal_error=f'{type(exc).__name__}: {exc}'
            logging.exception('Hangfordítási munkamenet hiba')
            self.failed.emit('Hangfordítási hiba: '+self._fatal_error)
        finally:
            self.recording_changed.emit(False)
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            try:
                self._checkpoint()
            except Exception:
                logging.exception('Szövegkönyv helyreállítási mentési hiba')
            self.completed.emit(self.entries,self.started)

    def stop(self):
        """Finish recording; process what was captured."""
        self.stop_requested.set()

    def abort(self):
        """Used only when the whole application is shutting down."""
        self.cancel.set()
        self.stop_requested.set()

class ClickThroughSubtitle(QWidget):
    """Always click-through; stacked completed translations with newest at bottom."""
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool |
                         Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._rows = collections.deque(maxlen=60)
        self._raw_translation = ''
        self._font_size = 19
        self._display_original = False
        self._panel = QWidget(self)
        self._panel.setObjectName('liveSubtitlePanel')
        self._panel.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._translated = QLabel('')
        self._translated.setWordWrap(True)
        self._translated.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self._translated.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._translated.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._translated.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        inner = QVBoxLayout(self._panel)
        inner.setContentsMargins(14, 14, 14, 14)
        inner.addWidget(self._translated)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._panel)
        self.resize(410, 540)

    def set_presentation(self, cfg):
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        rect = screen.availableGeometry()
        width = max(250, min(int(cfg.get('width', 410)), rect.width()))
        height = max(180, min(int(cfg.get('height', 540)), rect.height()))
        self.resize(width, height)
        x_pct = int(cfg.get('x', 95)) / 100
        y_pct = int(cfg.get('y', 50)) / 100
        x = rect.x() + int((rect.width() - width) * x_pct)
        y = rect.y() + int((rect.height() - height) * y_pct)
        self.move(x, y)
        self.setWindowOpacity(max(.15, min(1, int(cfg.get('opacity', 85))/100)))
        self._font_size = max(12, min(42, int(cfg.get('font', 19))))
        self._display_original = bool(cfg.get('show_original', False))
        self._panel.setStyleSheet('QWidget#liveSubtitlePanel { background: rgba(12,20,34,215); border-radius: 14px; }')
        self._translated.setStyleSheet(f'color: white; font-size: {self._font_size}px; font-weight: 500;')
        self._refresh_visible_text()

    def _refresh_visible_text(self):
        from PySide6.QtGui import QFontMetrics
        if not self._rows:
            self._translated.setText('')
            return
        metrics = QFontMetrics(self._translated.font())
        width = max(70, self.width() - 34)
        height = max(70, self.height() - 34)
        flags = int(Qt.TextFlag.TextWordWrap)
        def fits(text):
            return metrics.boundingRect(QRect(0, 0, width, 100000), flags, text).height() <= height
        visible = []
        for item in reversed(self._rows):
            candidate = item if not visible else item + '\n\n' + '\n\n'.join(visible)
            if not fits(candidate):
                break
            visible.insert(0, item)
        if not visible:
            newest = self._rows[-1]
            words = newest.split()
            lo, hi, result = 0, len(words), ''
            while lo <= hi:
                n = (lo + hi) // 2
                candidate = '… ' + ' '.join(words[-n:]) if n else ''
                if fits(candidate):
                    result = candidate
                    lo = n + 1
                else:
                    hi = n - 1
            visible = [result or metrics.elidedText(newest[-100:], Qt.TextElideMode.ElideLeft, width)]
        self._translated.setText('\n\n'.join(visible))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_visible_text()

    def show_text(self, original, magyar):
        """original is a speaker or section label in batch mode."""
        if not magyar:
            return
        self._raw_translation = magyar
        label = (original.strip() + ': ') if original else ''
        # Split ONLY completed Hungarian translations for readable vertical stacking.
        # This does not influence capture/STT segmentation or what is saved.
        sentences = re.split(r'(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÖŐÚÜŰ0-9„\"])', magyar.strip())
        for i, sentence in enumerate(sentences):
            if sentence.strip():
                self._rows.append((label if i == 0 else '') + sentence.strip())
        self._refresh_visible_text()
        if not self.isVisible():
            self.show()

    def clear_session(self):
        self._rows.clear()
        self._raw_translation = ''
        self._refresh_visible_text()

def formatted_transcript(entries, started, game_title='', show_original=False):
    """HTML and plain metadata for the embedded, scrollable transcript."""
    metadata = f'Felvétel: {started}  •  {len(entries)} beszédrészlet'
    if game_title:
        metadata += f'  •  Játék (feltételezett): {game_title}'
    chunks = ['<html><body style="font-family:Segoe UI,sans-serif;font-size:14px;">']
    previous = None
    for entry in entries:
        speaker = str(entry.get('speaker') or 'Ismeretlen beszélő')
        if speaker != previous:
            chunks.append('<h3 style="color:#86c6ff;margin:19px 0 6px;">' + html.escape(speaker) + '</h3>')
            previous = speaker
        timestamp = html.escape(str(entry.get('time') or ''))
        if timestamp:
            chunks.append('<div style="color:#9aacc8;font-size:11px;margin:10px 0 3px;">'
                          + timestamp + '</div>')
        translated = str(entry.get('magyar') or '')
        error = str(entry.get('error') or '')
        if translated:
            chunks.append('<p style="margin:5px 0 13px;line-height:1.5;">'
                          + html.escape(translated).replace('\n', '<br>') + '</p>')
        elif error:
            chunks.append('<p style="color:#e5a8a8;">Fordítás nem sikerült: '
                          + html.escape(error) + '</p>')
        if show_original and entry.get('original'):
            chunks.append('<p style="color:#9ca9bb;font-size:12px;margin:0 0 12px;">'
                          + html.escape(str(entry['original'])).replace('\n','<br>') + '</p>')
    chunks.append('</body></html>')
    return metadata, ''.join(chunks)


def formatted_saved_transcript(saved_text):
    """Render an existing plain-text audio history entry as structured HTML."""
    lines = saved_text.splitlines()
    parts = ['<html><body style="font-family:Segoe UI,sans-serif;font-size:14px;">']
    if lines:
        parts.append('<p style="color:#93a9c9;font-size:12px;">' + html.escape(lines[0]) + '</p>')
    for block in re.split(r'\n\s*\n', '\n'.join(lines[1:])):
        block = block.strip()
        if not block:
            continue
        inner = block.splitlines()
        label = inner[0]
        # Saved records start with an ISO time and an optional speaker label.
        if label.startswith('[') and '] ' in label:
            time_part, speaker = label.split('] ', 1)
            parts.append('<div style="margin-top:15px;color:#86c6ff;font-size:12px;">' +
                         html.escape(time_part + '] ' + speaker) + '</div>')
            inner = inner[1:]
        if inner:
            parts.append('<p style="margin:5px 0 12px;line-height:1.5;">' +
                         '<br>'.join(html.escape(x) for x in inner) + '</p>')
    parts.append('</body></html>')
    return ''.join(parts)


class RecordingIndicator(QWidget):
    """A small, user-draggable, animated red microphone; no game overlay text."""
    def __init__(self, cfg, moved):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(66, 66)
        self.moved_callback = moved
        self._drag_from = None
        self._phase = 0
        self.icon = QLabel('🎙', self)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setGeometry(4, 4, 58, 58)
        self.icon.setStyleSheet('font-size:28px;color:#ffffff;background:transparent;')
        self.icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._pulse)
        self.move(int(cfg.get('indicator_x', 90)), int(cfg.get('indicator_y', 90)))

    def _pulse(self):
        self._phase = (self._phase + 1) % 24
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pulse = abs(12 - self._phase) / 12
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(245, 50, 62, int(65 + (1-pulse)*85)))
        p.drawEllipse(1, 1, 64, 64)
        p.setBrush(QColor(193, 14, 37, int(175 + (1-pulse)*80)))
        p.drawEllipse(8, 8, 50, 50)

    def start(self):
        self._phase = 0
        self.timer.start(75)
        self.show()

    def stop(self):
        self.timer.stop()
        self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = event.globalPosition().toPoint() - self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_from is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_from is not None:
            self._drag_from = None
            self.moved_callback(self.pos())
        super().mouseReleaseEvent(event)


class LiveTranslationSettings(QWidget):
    transcript_ready = Signal(list, str, str, bool)
    processing_started = Signal()
    processing_status = Signal(str)
    processing_empty = Signal(str)
    game_inferred = Signal(str)
    recording_state = Signal(bool)
    """All subtitle interaction is intentionally confined to this settings window."""
    def __init__(self, app_dir, history_callback, app_config_provider=None, game_detector=None):
        super().__init__()
        self._open_settings_callback = None
        self._close_settings_callback = None
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.app_dir = Path(app_dir)
        self.path = self.app_dir / 'hangforditas_beallitasok.json'
        self.recovery_path = self.app_dir / 'hangforditas_folyamatban.json'
        self.on_history = history_callback
        self.app_config_provider = app_config_provider
        self.game_detector = game_detector
        self.text_model_loader = None
        self.worker = None
        self.model_loader = None
        self.device_loader = None
        self.subtitle = ClickThroughSubtitle()  # Kept for main-app shutdown compatibility; never shown.
        self.transcript_window = None  # Legacy placeholder; results use the main overlay.
        defaults = {'url': DEFAULT_URL, 'model': DEFAULT_MODEL, 'opacity': 85, 'width': 410,
                    'height': 540, 'font': 19, 'x': 95, 'y': 50, 'show_original': False, 'device': '',
                    'use_app_text_api': True, 'text_url': '', 'text_model': '',
                    'text_fallback_model': '',
                    'result_width':560,'result_height':680,'result_x':100,'result_y':100}
        try:
            existing = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, ValueError):
            existing = {}
        self.cfg = dict(defaults, **existing)
        if self.cfg.get('model') in ('gemini-3.5-live-translate-preview', 'gemini-3.5-transcribe-live'):
            self.cfg['model'] = DEFAULT_MODEL
            # Migrate the previous wide/short overlay to a narrow reading column.
            if (int(self.cfg.get('width', 700)), int(self.cfg.get('height', 135))) in ((700, 135), (700, 150)):
                self.cfg.update(width=410, height=540, font=19, x=95, y=50)
        self._make_ui()
        self.indicator = RecordingIndicator(self.cfg, self._indicator_moved)
        self.load_devices()

    def _make_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 15, 16, 15)
        layout.setSpacing(9)
        self.setObjectName('audioSettingsContent')
        self.setStyleSheet('''
            QWidget#audioSettingsContent { background: #192337; color: #e9f0fa;
                border: 1px solid #304057; border-radius: 12px; }
            QWidget#audioSettingsContent QLabel, QWidget#audioSettingsContent QCheckBox { color: #e9f0fa; }
            QWidget#audioSettingsContent QLineEdit, QWidget#audioSettingsContent QComboBox,
            QWidget#audioSettingsContent QSpinBox { background: #101a2a; color: #ecf3fb;
                border: 1px solid #3d526e; border-radius: 6px; padding: 5px; }
            QWidget#audioSettingsContent QPushButton { background: #253348; color: #e7f0fb;
                border: 1px solid #354962; border-radius: 8px; padding: 7px; }
            QWidget#audioSettingsContent QPushButton:hover { background: #344863; }
        ''')
        title = QLabel('HANGFELVÉTEL ÉS UTÓLAGOS FORDÍTÁS')
        title.setStyleSheet('font-size:18px;font-weight:600')
        layout.addWidget(title)
        note = QLabel('Indításkor folyamatosan rögzíti a hangot. Leállítás után a Gemini átiratot készít, a fordító AI pedig magyar szövegkönyvet állít elő. A kész szövegkönyv a képi fordítás ablakában nyílik meg, mozgatható, méretezhető és görgethető.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.url = QLineEdit(self.cfg['url'])
        form.addRow('API URL', self.url)
        self.key = QLineEdit(keyring.get_password(VAULT_SERVICE, VAULT_ACCOUNT) or '')
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('API-kulcs', self.key)
        self.models = QComboBox()
        self.models.setEditable(True)
        self.models.addItem(self.cfg['model'])
        refresh_models = QPushButton('Modellek lekérése')
        refresh_models.clicked.connect(self.load_models)
        model_row = QHBoxLayout()
        model_row.addWidget(self.models, 1)
        model_row.addWidget(refresh_models)
        self.model_button = refresh_models
        form.addRow('Beszédfelismerő AI', model_row)
        self.devices = QComboBox()
        self.devices.addItem('Hangeszközök keresése…', None)
        device_row = QHBoxLayout()
        device_row.addWidget(self.devices, 1)
        refresh_devices = QPushButton('Frissítés')
        refresh_devices.clicked.connect(self.load_devices)
        device_row.addWidget(refresh_devices)
        self.device_button = refresh_devices
        form.addRow('Hangforrás', device_row)
        stt_note = QLabel('A Gemini 3.5 Transcribe a felvétel lezárása után készít átiratot és különíti el a beszélőket. Hosszú felvételnél a feldolgozás több részletben történik.')
        stt_note.setWordWrap(True)
        layout.addWidget(stt_note)
        text_title = QLabel('SZÖVEGES AI-FORDÍTÓ')
        text_title.setStyleSheet('font-size: 16px; font-weight: 600;')
        layout.addWidget(text_title)
        self.use_main_api = QCheckBox('A képernyőfordító meglévő API-kapcsolatának használata')
        self.use_main_api.setChecked(bool(self.cfg.get('use_app_text_api', True)))
        self.use_main_api.toggled.connect(self._text_api_mode_changed)
        layout.addWidget(self.use_main_api)
        text_form = QFormLayout()
        current_app = self._main_config()
        self.text_url = QLineEdit(self.cfg.get('text_url') or current_app.get('api_url', ''))
        self.text_url_label = QLabel('Fordító API URL')
        text_form.addRow(self.text_url_label, self.text_url)
        self.text_key = QLineEdit(keyring.get_password(VAULT_SERVICE, 'live-text-api-key') or '')
        self.text_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.text_key_label = QLabel('Fordító API-kulcs')
        text_form.addRow(self.text_key_label, self.text_key)
        self.text_model = QComboBox()
        self.text_model.setEditable(True)
        self.text_model.addItem(self.cfg.get('text_model') or current_app.get('model', ''))
        self.text_model_button = QPushButton('Fordító modellek lekérése')
        self.text_model_button.clicked.connect(self.load_text_models)
        text_row = QHBoxLayout()
        text_row.addWidget(self.text_model, 1)
        text_row.addWidget(self.text_model_button)
        text_form.addRow('Fordítómodell', text_row)
        self.text_fallback = QComboBox()
        self.text_fallback.setEditable(True)
        self.text_fallback.addItem('')
        self.text_fallback.setCurrentText(self.cfg.get('text_fallback_model', ''))
        text_form.addRow('Tartalék modell (opcionális)', self.text_fallback)
        layout.addLayout(text_form)
        self._text_api_mode_changed()

        self.positions = {}
        self.original=QCheckBox('Az eredeti nyelvű szöveg is látható a szövegkönyvben')
        self.original.setChecked(bool(self.cfg.get('show_original',False)))
        form.addRow('',self.original)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.start_button = QPushButton('Hangfelvétel indítása')
        self.start_button.clicked.connect(self.toggle)
        actions.addWidget(self.start_button)
        save = QPushButton('Beállítások mentése')
        save.clicked.connect(self.save_settings)
        actions.addWidget(save)
        layout.addLayout(actions)
        self.status = QLabel('Készen áll.')
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        back = QPushButton('Vissza az előző nézethez')
        back.clicked.connect(self.close_settings)
        layout.addWidget(back)

    def _main_config(self):
        if self.app_config_provider:
            try:
                return self.app_config_provider()
            except Exception:
                logging.exception('A képernyőfordító konfigurációja nem olvasható.')
        return {}

    def _text_api_mode_changed(self, *_):
        main = self.use_main_api.isChecked()
        for widget in (self.text_url, self.text_key, self.text_url_label, self.text_key_label):
            widget.setVisible(not main)
        if main:
            cfg = self._main_config()
            self.text_url.setPlaceholderText(cfg.get('api_url', ''))
        self.text_model_button.setEnabled(True)

    def load_text_models(self):
        if self.text_model_loader and self.text_model_loader.isRunning():
            return
        cfg = self._main_config() if self.use_main_api.isChecked() else {}
        url = (cfg.get('api_url') if cfg else self.text_url.text()).strip()
        key = cfg.get('api_key', '') if cfg else self.text_key.text().strip()
        if not url:
            self.status.setText('Előbb állítsd be a fordító AI URL-jét.')
            return
        self.text_model_button.setEnabled(False)
        self.status.setText('Fordító modellek lekérése…')
        self.text_model_loader = TextModels(url, key)
        self.text_model_loader.loaded.connect(self._text_models_loaded)
        self.text_model_loader.failed.connect(lambda msg: self.status.setText('Fordítómodell-hiba: ' + msg))
        self.text_model_loader.finished.connect(lambda: self.text_model_button.setEnabled(True))
        self.text_model_loader.start()

    def _text_models_loaded(self, values):
        current = self.text_model.currentText().strip()
        self.text_model.clear()
        self.text_model.addItems(values)
        if current and self.text_model.findText(current) < 0:
            self.text_model.insertItem(0, current)
        self.text_model.setCurrentText(current)
        previous_fallback = self.text_fallback.currentText().strip()
        self.text_fallback.clear()
        self.text_fallback.addItem('')
        self.text_fallback.addItems(values)
        if previous_fallback and self.text_fallback.findText(previous_fallback) < 0:
            self.text_fallback.addItem(previous_fallback)
        self.text_fallback.setCurrentText(previous_fallback)
        self.status.setText(f'{len(values)} szöveges modell betöltve.')

    def update_presentation(self, *_):
        self.cfg['show_original'] = self.original.isChecked()

    def _window_geometry_changed(self, window, persist=False):
        if not hasattr(self,'cfg') or window is None:
            return
        self.cfg.update(result_x=window.x(),result_y=window.y(),
                        result_width=window.width(),result_height=window.height())
        if persist:
            try:
                tmp=self.path.with_suffix('.tmp')
                tmp.write_text(json.dumps(self.cfg,ensure_ascii=False,indent=2),encoding='utf-8')
                tmp.replace(self.path)
            except OSError:
                logging.exception('A fordításablak pozícióját nem sikerült menteni.')

    def close_settings(self):
        self.save_settings()
        if self._close_settings_callback:
            self._close_settings_callback()

    def save_settings(self):
        self.update_presentation()
        try:
            self.cfg['url'] = safe_api_url(self.url.text())
            model = self.models.currentText().strip().removeprefix('models/')
            if not model:
                raise ValueError('Válassz beszédfelismerő AI-modellt.')
            if model != 'gemini-3.5-transcribe':
                raise ValueError('A beszélőfelismerős módhoz jelenleg a gemini-3.5-transcribe támogatott.')
            self.cfg['model'] = model
            self.cfg['device'] = self.devices.currentData() or ''
            self.cfg.pop('game_hint', None)
            self.cfg['use_app_text_api'] = self.use_main_api.isChecked()
            self.cfg['text_url'] = self.text_url.text().strip()
            self.cfg['text_model'] = self.text_model.currentText().strip().removeprefix('models/')
            self.cfg['text_fallback_model'] = self.text_fallback.currentText().strip()
            if not self.cfg['text_model']:
                raise ValueError('Válassz szöveges fordító AI-modellt is.')
            if not self.use_main_api.isChecked():
                url = self.cfg['text_url']
                if not url.endswith('/chat/completions'):
                    raise ValueError('A szöveges fordító API URL /chat/completions útvonallal végződjön.')
                if self.text_key.text().strip():
                    keyring.set_password(VAULT_SERVICE, 'live-text-api-key', self.text_key.text().strip())
                else:
                    try:
                        keyring.delete_password(VAULT_SERVICE, 'live-text-api-key')
                    except keyring.errors.PasswordDeleteError:
                        pass
            # Store credentials only in the Windows user credential vault.
            secret = self.key.text().strip()
            if secret:
                keyring.set_password(VAULT_SERVICE, VAULT_ACCOUNT, secret)
            else:
                try:
                    keyring.delete_password(VAULT_SERVICE, VAULT_ACCOUNT)
                except keyring.errors.PasswordDeleteError:
                    pass
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(self.path)
            self.status.setText('Hangfordítási beállítások elmentve.')
            return True
        except Exception as exc:
            self.status.setText('Mentési hiba: ' + str(exc))
            return False

    def load_devices(self):
        if self.device_loader and self.device_loader.isRunning():
            return
        self.device_button.setEnabled(False)
        self.device_loader = Devices()
        self.device_loader.loaded.connect(self.devices_loaded)
        self.device_loader.failed.connect(lambda s: self.status.setText('Hangeszközhiba: ' + s))
        self.device_loader.finished.connect(lambda: self.device_button.setEnabled(True))
        self.device_loader.start()

    def devices_loaded(self, devices):
        self.devices.clear()
        for name, identifier in devices:
            self.devices.addItem(name, identifier)
        if not devices:
            self.devices.addItem('Nem található hangkimenet', None)
        index = self.devices.findData(self.cfg.get('device'))
        if index >= 0:
            self.devices.setCurrentIndex(index)

    def load_models(self):
        if self.model_loader and self.model_loader.isRunning():
            return
        if not self.key.text().strip():
            self.status.setText('Add meg a Gemini API-kulcsot.')
            return
        try:
            url = safe_api_url(self.url.text())
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.model_button.setEnabled(False)
        self.status.setText('Modelllista lekérése…')
        self.model_loader = Models(self.key.text().strip(), url)
        self.model_loader.loaded.connect(self.models_loaded)
        self.model_loader.failed.connect(lambda s: self.status.setText('Modelllista hiba: ' + s))
        self.model_loader.finished.connect(lambda: self.model_button.setEnabled(True))
        self.model_loader.start()

    def models_loaded(self, models):
        current = self.models.currentText().strip()
        self.models.clear()
        self.models.addItems(models)
        if current and self.models.findText(current) < 0:
            self.models.insertItem(0, current)
        self.models.setCurrentText(current or DEFAULT_MODEL)
        self.status.setText(f'{len(models)} modell lekérve. A beszélők elkülönítéséhez gemini-3.5-transcribe modellt válassz.')

    def toggle(self):
        if self.worker and self.worker.isRunning():
            if self.worker.stop_requested.is_set():
                self.status.setText('A felvétel feldolgozása már folyamatban van…')
                return
            self.worker.stop()
            self._recording_changed(False)
            self.processing_started.emit()
            self.start_button.setEnabled(False)
            self.status.setText('Felvétel lezárva – átírás és fordítás folyamatban…')
            return
        if not self.save_settings():
            return
        recognized_game = (self.game_detector() if self.game_detector else '') or ''
        key = self.key.text().strip()
        device = self.devices.currentData()
        if not key or device is None:
            self.status.setText('API-kulcs és hangkimenet megadása szükséges.')
            return
        self.subtitle.hide()
        current = self._main_config() if self.use_main_api.isChecked() else {}
        translation_url = current.get('api_url', '') if self.use_main_api.isChecked() else self.cfg['text_url']
        translation_key = current.get('api_key', '') if self.use_main_api.isChecked() else self.text_key.text().strip()
        translation_model = self.cfg['text_model']
        if not translation_url:
            self.status.setText('A szöveges fordító API URL-je nincs beállítva.')
            return
        self.worker = LiveWorker(key, self.cfg['url'], self.cfg['model'], device, self.recovery_path,
                                 translation_url, translation_key, translation_model,
                                 self.cfg.get('text_fallback_model', ''),
                                 game_hint='')
        self._provided_game = recognized_game
        self.worker.detected_game = recognized_game
        self.worker.inferred_game = recognized_game
        # A felirat csak a teljes felvétel feldolgozása után jelenik meg.
        self.worker.status.connect(self._worker_status)
        self.worker.recording_changed.connect(self._recording_changed)
        self.worker.failed.connect(self._worker_error)
        self.worker.completed.connect(self._completed)
        self.worker.finished.connect(self._finished)
        self.worker.start()
        self.start_button.setText('Rögzítés leállítása és feldolgozás')

    def _indicator_moved(self, pos):
        self.cfg['indicator_x'] = pos.x()
        self.cfg['indicator_y'] = pos.y()
        try:
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(self.path)
        except OSError:
            logging.exception('Felvételjelző helyzetének mentése nem sikerült.')

    def _recording_changed(self, recording):
        # Late queued start signals must not reactivate the indicator after Stop.
        if recording and self.worker and self.worker.stop_requested.is_set():
            return
        if recording:
            self.indicator.start()
        else:
            self.indicator.stop()
        self.recording_state.emit(recording)

    def _worker_status(self, message):
        self.status.setText(message)
        if self.worker and self.worker.stop_requested.is_set():
            self.processing_status.emit(message)

    def _worker_error(self, message):
        self.status.setText('Hiba: ' + message)
        # Preserve the existing translated subtitle, if one was received.
        # If no subtitle was produced, display a short explanation instead.
        if not self.subtitle._raw_translation:
            self.status.setText('Hangfordítási hiba – részletek a beállításokban: ' + message)

    def _completed(self, entries, started):
        if (self.worker and self.worker.inferred_game
                and self.worker.inferred_game != getattr(self, '_provided_game', '')):
            self.game_inferred.emit(self.worker.inferred_game)
        if not entries:
            message = ('A felvételben nem találtam fordítható beszédet, '
                       'vagy a feldolgozás hibával leállt.')
            if self.worker and self.worker._fatal_error:
                message += '\n\nHiba: ' + self.worker._fatal_error
            self.status.setText(message)
            self.processing_empty.emit(message)
            return
        if entries:
            self.transcript_ready.emit(
                entries, started,
                (self.worker.inferred_game if self.worker else ''),
                bool(self.cfg.get('show_original', False)))
            chunks = []
            for entry in entries:
                lines = [f"[{entry['time']}] {entry.get('speaker', '')}"]
                if self.cfg.get('show_original', False) and entry.get('original'):
                    lines.append(str(entry['original']))
                if entry.get('magyar'):
                    lines.append(str(entry['magyar']))
                chunks.append('\n'.join(lines))
            body = 'Hangfordítás – ' + started + '\n\n' + '\n\n'.join(chunks)
            saved = self.on_history(body, (self.worker.inferred_game if self.worker else ''))
            if saved:
                if not (self.worker and self.worker._fatal_error):
                    self.status.setText(f'{len(entries)} részlet mentve a közös előzményekbe.')
                try:
                    self.recovery_path.unlink(missing_ok=True)
                except OSError:
                    pass
            else:
                self.status.setText('Az előzmények mentése sikertelen. A helyreállítási JSON megmaradt.')

    def _finished(self):
        failed = bool(self.worker and self.worker._fatal_error)
        if failed:
            # Leave the final subtitle or error message visible briefly so that
            # it cannot disappear the instant the worker finishes.
            current_worker = self.worker
            QTimer.singleShot(12000, lambda: self.subtitle.hide()
                              if self.worker is current_worker and not self.worker.isRunning()
                              else None)
        else:
            self.subtitle.hide()
        self.start_button.setEnabled(True)
        self.start_button.setText('Hangfelvétel indítása')

    def open_settings(self):
        if self._open_settings_callback:
            self._open_settings_callback()
        else:
            self.show()

    def request_shutdown(self):
        self.indicator.stop()
        if self.worker and self.worker.isRunning():
            self.worker.abort()
            return True
        return False

    def closeEvent(self, event):
        # Closing settings MUST NOT stop an active background translation.
        self.save_settings()
        event.accept()
